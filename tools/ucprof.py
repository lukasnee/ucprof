import sys
import time
import json
from collections import namedtuple
import argparse
import re

Packet = namedtuple("Packet", ["typ", "cycle_cnt", "fn", "context"])
Symbol = namedtuple("Symbol", ["address", "typ", "fn_name", "file", "line"])
NM_SYMBOLS_REGEX_PATTERN = r"(?P<address>[0-9a-f]+)\s(?P<typ>\w)\s(?P<fn_name>[^\t\n]*)(\t(?P<file>.*):(?P<line>\d+))?"
Event = namedtuple("Event", ["timestamp", "typ",
                   "filename", "line", "name", "context"])

# REPLACE custom logger with python logging module
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
                    file.seek(-3, 1)
                    continue
                cycle_cnt = int.from_bytes(file.read(4), byteorder='little')
                context = int.from_bytes(file.read(4), byteorder='little')
                fn = int.from_bytes(file.read(4), byteorder='little')
                packets.append(Packet(typ, cycle_cnt, fn, context))
        self.log_info(0, f'Packets parsed: {len(packets)}')
        return packets

    def __within_begin_boundry(self, timestamp):
        return self.args.begin is None or timestamp >= self.args.begin

    def __within_end_boundry(self, timestamp):
        return self.args.end is None or timestamp <= self.args.end

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

    def __parse_packets(self, symbols, packets):
        # profile is a list of events of a particular thread
        profiles = []
        shared_frames_registry = {}
        shared_frames = []
        for idx, packet in enumerate(packets):

            if context_is_interrupt(packet.context):
                self.log_debug(
                    2, f'__parse_packets: {idx} packet skipped - interrupt')
                continue

            timestamp = self.__calculate_timestamp(packet.cycle_cnt)
            if not self.__within_begin_boundry(timestamp):
                self.log_debug(
                    4, f'__parse_packets: {idx} packet skipped - before --begin')
                continue

            if not self.__within_end_boundry(timestamp):
                self.log_debug(
                    3, f'__parse_packets: {idx} packet skipped - after --end')
                break

            if not self.__within_fw_boundry(packet.fn):
                self.log_debug(
                    2, f'__parse_packets: {idx} packet skipped - not within firmware memory region, {packet.fn:08x}')
                continue
            symbol = next(
                (s for s in reversed(symbols) if packet.fn >= s.address), None)

            if not symbol:
                symbol = Symbol(
                    0, "U", "fn @ 0x{:08x}".format(packet.fn), "", 0)

            shared_frame_key = (symbol.file, symbol.line, symbol.fn_name)
            if shared_frame_key not in shared_frames_registry:
                shared_frames_registry[shared_frame_key] = len(shared_frames)
                shared_frames.append(
                    {"name": symbol.fn_name, "file": symbol.file, "line": symbol.line, "col": 1})
            frame_index = shared_frames_registry[shared_frame_key]

            if not any(profile['name'] == "0x{:08x}".format(packet.context) for profile in profiles):
                profiles.append(
                    {"type": "evented", "name": "0x{:08x}".format(packet.context), "unit": "seconds", "startValue": 0.0, "endValue": 0.0, "events": []})
            profile = next(
                (p for p in profiles if p['name'] == "0x{:08x}".format(packet.context)), None)
            if not profile:
                self.log_error(
                    0, f'Profile not found: {"0x{:08x}".format(packet.context)}')
                continue
            profile['events'].append(
                {"type": packet.typ, "at": timestamp, "frame": frame_index})
            self.log_trace(
                3, f"{profile['name']}: {packet.typ} {timestamp:.9f} {frame_index}")

        for profile in profiles:
            # remove all closing events at the beginning
            while len(profile['events']) > 1 and profile['events'][0]['type'] == "C":
                profile['events'].pop(0)

            # remove all events that have zero start time
            while profile and profile['events'][0]['at'] == 0.0:
                profile['events'].pop(0)

        self.log_info(0, f'Profiles parsed: {len(profiles)}')
        for profile in profiles:
            print(f"  {profile['name']}: {len(profile['events'])} events")

        shared_frames.append(
            {"name": "OVERFLOW!", "file": "", "line": 0, "col": 1})
        self.overflow_frame_index = len(shared_frames) - 1

        earliest_start = min(
            [profile['events'][0]['at'] for profile in profiles])
        latest_end = max(
            [profile['events'][-1]['at'] for profile in profiles])

        for profile in profiles:
            profile['events'] = self.__fix_events(
                profile['events'], shared_frames)
            # pick the same time range for all threads
            profile['startValue'] = earliest_start
            profile['endValue'] = latest_end

        return {
            "$schema": "https://www.speedscope.app/file-format-schema.json",
            "profiles": profiles,
            "shared": {"frames": shared_frames},
            "exporter": "lukasnee/ucprof",
        }

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

        # ensure events are in cronological order by finding last chronological sequence and trimming the rest
        last_break_idx = 0
        for idx, event in enumerate(events):
            if idx == 0:
                continue
            if event['at'] < events[idx-1]['at']:
                last_break_idx = idx
        events = events[last_break_idx:]

        call_stack = []
        fixed_events = []
        overflow = False
        for idx, event in enumerate(events):

            if event['type'] == "C":
                # TODO think of better ways to handle broken frames
                # TODO make the breaks more visible in the speedscope GUI
                if not call_stack:
                    self.__log_closing_event(
                        "W", 1, idx, event['at'], frames[event['frame']], call_stack, frames, "Call stack is empty - skipping")
                    call_stack = []
                    continue
                if call_stack[-1] != event['frame']:
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
                call_stack.append(event['frame'])

        # "C" all remaining frames
        for frame in reversed(call_stack):
            fixed_events.append(
                {"type": "C", "at": event['at'], "frame": frame})

        return fixed_events

    def __export_to_json(self, speedscope_dict, filename):
        with open(filename, "w") as f:
            json.dump(speedscope_dict, f, indent=2)

    def fold_all_stacks(self, args):
        if not args.nm_symbols_path or not args.frame_data_path:
            self.log_info(0, "Please provide both input file paths.")
            return
        self.args = args
        symbols = self.__parse_nm_symbols()
        packets = self.__read_packets_from_file()
        speedscope_dict = self.__parse_packets(symbols, packets)
        filename = f"{args.frame_data_path.split('/')[-1].split('.')[0]}.json"
        self.__export_to_json(speedscope_dict, filename)
        print(f"Exported {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tool for processing a ucprof binary record.")
    parser.add_argument("nm_symbols_path", help="Symbol file path")
    parser.add_argument("frame_data_path", help="Frame data file path")
    parser.add_argument("--begin", type=float,
                        help="Timestamp from in seconds")
    parser.add_argument("--end", type=float, help="Timestamp to in seconds")
    parser.add_argument("--clk_freq", type=int, default=480000000,
                        help="Clock frequency used for timestamps")
    parser.add_argument("--verbosity", "-v", type=int, default=0)
    parser.add_argument("--fw_base", type=int, default=0x24000000)
    parser.add_argument("--fw_size", type=int, default=0x80000)
    parser.add_argument("--no_color", action="store_true")
    parser.add_argument("--top", type=int, default=10,
                        help="Process only the top most eventful threads")
    args = parser.parse_args()
    ucProf = UcProf()
    ucProf.fold_all_stacks(args)
