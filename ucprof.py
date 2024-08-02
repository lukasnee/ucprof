import sys
import time
import json
from collections import namedtuple
import argparse
import re

Packet = namedtuple("Packet", ["typ", "cycle_cnt", "this_fn", "context"])
Symbol = namedtuple("Symbol", ["address", "typ", "fn_name", "file", "line"])
NM_SYMBOLS_REGEX_PATTERN = r"(?P<address>[0-9a-f]+)\s(?P<typ>\w)\s(?P<fn_name>[^\t\n]*)(\t(?P<file>.*):(?P<line>\d+))?"
Event = namedtuple("Event", ["timestamp", "typ",
                   "filename", "line", "name", "context"])

COLORS = {
    'RED': '\033[91m',
    'YELLOW': '\033[93m',
    'PURPLE': '\033[95m',
    'CYAN': '\033[96m',
    'RESET': '\033[0m'
}


def context_is_interrupt(context):
    return context == 0


class UcProf:

    def __init__(self):
        self.args = None
        # TODO the following variables should not be class variables
        self._begin_cycle_cnt_offset = None
        self._last_cycle_cnt = 0

    def print(self, verbosity, *args, **kwargs):
        if self.args.verbosity >= verbosity:
            print(*args, **kwargs)

    def __log(self, verbosity, type, color, *args, **kwargs):
        color = "" if self.args.no_color else color
        self.print(verbosity, f"{color}{type}|", *args, **kwargs)
        if color != "" and color != COLORS['RESET']:
            self.print(verbosity, f"{COLORS['RESET']}", *args, **kwargs)

    def log(self, type, verbosity, *args, **kwargs):
        if type == 'E':
            self.log_error(verbosity, *args, **kwargs)
        elif type == 'W':
            self.log_warning(verbosity, *args, **kwargs)
        elif type == 'I':
            self.log_info(verbosity, *args, **kwargs)
        elif type == 'D':
            self.log_debug(verbosity, *args, **kwargs)
        elif type == 'T':
            self.log_trace(verbosity, *args, **kwargs)

    def log_error(self, verbosity, *args, **kwargs):
        self.__log(verbosity, 'E', COLORS['RED'], *args, **kwargs)

    def log_warning(self, verbosity, *args, **kwargs):
        self.__log(verbosity, 'W', COLORS['YELLOW'], *args, **kwargs)

    def log_info(self, verbosity, *args, **kwargs):
        self.__log(verbosity, 'I', COLORS['RESET'], *args, **kwargs)

    def log_debug(self, verbosity, *args, **kwargs):
        self.__log(verbosity, 'D', COLORS['PURPLE'], *args, **kwargs)

    def log_trace(self, verbosity, *args, **kwargs):
        self.__log(verbosity, 'T', COLORS['CYAN'], *args, **kwargs)

    def __parse_nm_symbols(self):
        symbols = []
        with open(args.nm_symbols_path, 'r') as file:
            for line in file:
                match = re.match(NM_SYMBOLS_REGEX_PATTERN, line)
                if match:
                    symbol = Symbol(
                        int(match.group("address"), 16),
                        match.group("typ"),
                        match.group("fn_name"),
                        match.group("file") if match.group("file") else "",
                        int(match.group("line")) if match.group("line") else 0
                    )
                    if symbol.typ in ['a', 'A', 'b', 'B', 'd', 'D', 'r', 'R', 'V']:
                        continue  # skip symbols that are not functions
                    index = 0
                    while index < len(symbols) and symbol.address > symbols[index].address:
                        index += 1
                    symbols.insert(index, symbol)
        self.log_info(0, f'Symbols parsed: {len(symbols)}')
        return symbols

    def __read_packets_from_file(self):
        packets = []
        with open(args.frame_data_path, 'rb') as file:
            while True:
                typ = file.read(4)
                if not typ:
                    break
                if typ == b'O\x00\x00\x00':
                    typ = 'O'
                elif typ == b'C\x00\x00\x00':
                    typ = 'C'
                else:
                    continue
                cycle_cnt = int.from_bytes(file.read(4), byteorder='little')
                context = int.from_bytes(file.read(4), byteorder='little')
                this_fn = int.from_bytes(file.read(4), byteorder='little')
                packets.append(Packet(typ, cycle_cnt, this_fn, context))
        self.log_info(0, f'Packets parsed: {len(packets)}')
        return packets

    def __within_begin_boundry(self, event):
        return self.args.begin is None or event.timestamp >= self.args.begin

    def __within_end_boundry(self, event):
        return self.args.end is None or event.timestamp <= self.args.end

    def __within_fw_boundry(self, addr):
        return self.args.fw_base <= addr < self.args.fw_base + self.args.fw_size

    def __calculate_timestamp(self, cycle_cnt):

        # offset the begin time
        if self._begin_cycle_cnt_offset is None:
            self._begin_cycle_cnt_offset = cycle_cnt

        # handle overflow
        if cycle_cnt < self._last_cycle_cnt:
            cycle_cnt = cycle_cnt + 2**32
        self._last_cycle_cnt = cycle_cnt

        return (cycle_cnt - self._begin_cycle_cnt_offset) / self.args.clk_freq

    def __packet_to_event(self, symbols, packet):
        typ, cycle_cnt, this_fn, context = packet
        timestamp = self.__calculate_timestamp(cycle_cnt)

        if not self.__within_fw_boundry(this_fn):
            return None

        symbol = next(
            (s for s in reversed(symbols) if this_fn >= s.address), None)
        if symbol:
            name = symbol.fn_name
            filename = symbol.file
            line = symbol.line
        else:
            name = "fn @ 0x{:08x}".format(this_fn)
            filename = ""
            line = 0
        return Event(timestamp, typ, filename, line, name, context)

    def __compute_thread_stats(self, packets):
        thread_stats = {}
        for packet in packets:
            if packet.context in thread_stats:
                thread_stats[packet.context] += 1
            else:
                thread_stats[packet.context] = 1
        thread_stats = dict(
            sorted(thread_stats.items(), key=lambda x: x[1], reverse=True))
        VERBOSITY = 1
        self.log_info(VERBOSITY, '\ncontext,count')
        for context, count in thread_stats.items():
            if context_is_interrupt(context):
                self.log_info(VERBOSITY, f'interrupts,{count}')
            else:
                self.log_info(VERBOSITY, f'{context:08x},{count}')
        thread_stats.pop(0, None)  # remove interrupts
        self.log_info(VERBOSITY, f'\n')
        return thread_stats

    def __parse_events_from_packets(self, symbols, packets):
        events = []
        for idx, packet in enumerate(packets):
            if context_is_interrupt(packet.context):
                self.log_debug(
                    2, f'__parse_events_from_packets: {idx} event skipped - interrupt')
                continue
            event = self.__packet_to_event(symbols, packet)
            if not event:
                self.log_warning(
                    2, f'__parse_events_from_packets: {event} event skipped - not in firmware, {packet.this_fn:08x}')
                continue

            if not self.__within_begin_boundry(event):
                self.log_debug(
                    4, f'__parse_events_from_packets: {event} event skipped - before --begin')
                continue
            if not self.__within_end_boundry(event):
                self.log_debug(
                    3, f'__parse_events_from_packets: {event} event skipped - after --end')
                break
            events.append(event)
            self.log_trace(
                3, f'{event.timestamp:.2f} {packet.this_fn:08x} {event.typ} {event.name} {event.context:08x}')
        self.log_info(0, f'Events parsed: {len(events)}')
        return events

    def __print_call_stack(self, call_stack, frames):
        self.log_info(0, f"Call stack:")
        for depth, frame in enumerate(call_stack):
            indent = '  ' * depth
            self.log_info(0, f"{indent}{frames[frame]['name']}")
        self.log_info(0, f"")

    def __log_opening_event(self, severity, verbosity, idx, timestamp, frame, call_stack, frames, suffix=""):
        indent = '  ' * len(call_stack)
        self.log(severity, verbosity,
                 f"{idx:8d}|{timestamp:.9f}|{indent}{frame['name']}{': ' if suffix else ''}{suffix}")

    def __log_closing_event(self, severity, verbosity, idx, timestamp, frame, call_stack, frames, suffix=""):
        indent = '  ' * len(call_stack)
        self.log(severity, verbosity,
                 f"{idx:8d}|{timestamp:.9f}|{indent}~{frame['name']}{': ' if suffix else ''}{suffix}")

    def __fix_events(self, events, frames):
        call_stack = []
        fixed_events = []
        overflow = False
        for idx, event in enumerate(events):

            if event["type"] == "C":
                # TODO think of better ways to handle broken frames
                # TODO make the breaks more visible in the speedscope GUI
                if not call_stack:
                    self.__log_closing_event(
                        "W", 1, idx, event['at'], frames[event['frame']], call_stack, frames, "Call stack is empty - skipping")
                    call_stack = []
                    continue
                if call_stack[-1] != event["frame"]:
                    self.log_warning(
                        1, f"Call stack inconsistent on {idx} event: tried to close '{frames[event['frame']]['name']}' instead of '{frames[call_stack[-1]]['name']}'")
                    self.log_info(1, "Stack termination (begin)")
                    for frame in reversed(call_stack):
                        fixed_events.append(
                            {"type": "C", "at": events[idx-1]['at'], "frame": frame})
                        call_stack.pop()
                        self.__log_closing_event(
                            "I", 1, idx, event['at'], frames[frame], call_stack, frames)
                    self.log_info(1, "Stack termination (end)")
                    fixed_events.append(
                        {"type": "O", "at": events[idx-1]['at'], "frame": self.overflow_frame_index})
                    self.__log_opening_event(
                        "I", 1, idx, event['at'], frames[self.overflow_frame_index], call_stack, frames)
                    overflow = True
                    continue
                fixed_events.append(event)
                call_stack.pop()
                self.__log_closing_event(
                    "I", 1, idx, event['at'], frames[event['frame']], call_stack, frames)
            else:
                if overflow:
                    fixed_events.append(
                        {"type": "C", "at": event['at'], "frame": self.overflow_frame_index})
                    self.__log_closing_event(
                        "I", 1, idx, event['at'], frames[self.overflow_frame_index], call_stack, frames)
                    overflow = False
                self.__log_opening_event(
                    "I", 1, idx, event['at'], frames[event['frame']], call_stack, frames)
                fixed_events.append(event)
                call_stack.append(event["frame"])

        # "C" all remaining frames
        for frame in reversed(call_stack):
            fixed_events.append(
                {"type": "C", "at": event['at'], "frame": frame})

        return fixed_events

    def __make_speedscope_dict_from_events(self, events, context):

        # pick the same time range for all threads
        startValue = events[0].timestamp
        endValue = events[-1].timestamp

        # filter events by context
        events = [event for event in events if event.context == context]

        if not events:
            self.log_info(0, f"No events for context {context:08x}")
            return None

        # remove all closing events at the beginning
        while events[0].typ == "C":
            events.pop(0)

        # remove all frames that have zero start time
        while events and events[0].timestamp == 0.0:
            events.pop(0)

        frame_cache = {}
        frames = []
        dict_events = []
        for timestamp, typ, filename, line, name, context in events:
            key = (filename, line, name)
            if key not in frame_cache:
                frame_cache[key] = len(frames)
                frames.append(
                    {"name": name, "file": filename, "line": line, "col": 1})
            frame_index = frame_cache[key]
            dict_events.append(
                {"type": typ, "at": timestamp, "frame": frame_index})
        frames.append({"name": "OVERFLOW!", "file": "", "line": 0, "col": 1})
        self.overflow_frame_index = len(frames) - 1

        dict_events = self.__fix_events(dict_events, frames)

        return {
            "$schema": "https://www.speedscope.app/file-format-schema.json",
            "profiles": [
                {
                    "type": "evented",
                    "name": "ucProf",
                    "unit": "seconds",
                    "startValue": startValue,
                    "endValue": endValue,
                    "events": dict_events,
                }
            ],
            "shared": {"frames": frames},
            "activeProfileIndex": 0,
            "exporter": "UcProf",
            "name": "exported from sysview",
        }

    def __export_to_json(self, speedscope_dict, filename):
        with open(filename, "w") as f:
            json.dump(speedscope_dict, f, indent=2)
        print(f"Exported to {filename}")

    def fold_all_stacks(self, args):
        if not args.nm_symbols_path or not args.frame_data_path:
            self.log_info(0, "Please provide both input file paths.")
            return
        self.args = args
        symbols = self.__parse_nm_symbols()
        packets = self.__read_packets_from_file()
        thread_stats = self.__compute_thread_stats(packets)
        events = self.__parse_events_from_packets(symbols, packets)
        for thread_id in range(len(thread_stats) if len(thread_stats) < args.top else args.top):
            context = list(thread_stats.items())[thread_id][0]
            thread_speedscope_dict = self.__make_speedscope_dict_from_events(
                events, context)
            if not thread_speedscope_dict:
                continue
            filename = f"{args.frame_data_path.split('/')[-1].split('.')[0]}_{thread_id}.json"
            self.__export_to_json(thread_speedscope_dict, filename)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tool for processing a ucprof binary record.")
    parser.add_argument("nm_symbols_path", help="Symbol file path")
    parser.add_argument("frame_data_path", help="Frame data file path")
    parser.add_argument("--begin", type=float,
                        help="Timestamp from in seconds")
    parser.add_argument("--end", type=float, help="Timestamp to in seconds")
    parser.add_argument("--clk-freq", type=int, default=480000000,
                        help="Clock frequency used for timestamps")
    parser.add_argument("--verbosity", "-v", type=int, default=0)
    parser.add_argument("--fw-base", type=int, default=0x90000000)
    parser.add_argument("--fw-size", type=int, default=0x800000)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--top", type=int, default=10,
                        help="Process only the top most eventful threads")
    args = parser.parse_args()
    ucProf = UcProf()
    ucProf.fold_all_stacks(args)
