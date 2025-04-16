__author__ = "lukasnee"
__version__ = "0.1.0"

import time
import json
from collections import namedtuple
import argparse
import re
import logging
import struct

logger = logging.getLogger(__name__)

Symbol = namedtuple("Symbol", ["address", "typ", "fn_name", "file", "line"])
NM_SYMBOLS_REGEX_PATTERN = r"(?P<address>[0-9a-f]+)\s(?P<typ>\w)\s(?P<fn_name>[^\t\n]*)(\t(?P<file>.*):(?P<line>\d+))?"


def context_is_interrupt(context):
    return context == 0


class UcprofPacket:

    def __init__(self, data, fn_msb):
        if len(data) != 8:
            raise ValueError("Data must be exactly 8 bytes long")

        # Unpack the two 32-bit integers
        raw0, raw1 = struct.unpack("<II", data)  # Little-endian format

        # Decode the bitfields from the first 32-bit integer
        self.typ = 'C' if raw0 & 0x1 else 'O'
        self.context = (raw0 >> 1) & 0x7F
        self.fn = (fn_msb << 24) | ((raw0 >> 8) & 0xFFFFFF)
        self.cycle_cnt = raw1

    def __str__(self):
        return (f"UcprofPacket(typ={self.typ}, context=0x{self.context:02x}, "
                f"fn=0x{self.fn:08x}, cycle_cnt={self.cycle_cnt})")


class UcProf:

    def __init__(self, args):
        self.args = args
        # TODO the following variables should not be class variables
        self._begin_cycle_cnt_offset = None
        self._last_cycle_cnt = 0
        logging.basicConfig(level=args.log_level,
                            format="%(levelname)s| %(message)s")

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
        logger.info(f'Symbols parsed: {len(symbols)}')
        return symbols

    def __read_packets_from_file(self):
        packets = []
        with open(args.frame_data_path, 'rb') as file:
            while True:
                try:
                    packets.append(UcprofPacket(file.read(8), fn_msb=0x24))
                except ValueError:
                    logger.info("Reached end of file")
                    break
        logger.info(f'Packets parsed: {len(packets)}')
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

    def __parse_packets_into_speedscope_dict(self, symbols, packets):
        # profile is a list of events of a particular thread
        profiles = []
        shared_frames_registry = {}
        shared_frames = []
        for idx, packet in enumerate(packets):

            # if context_is_interrupt(packet.context):
            #     logger.log(
            #         logging.DEBUG-2, f'__parse_packets_into_speedscope_dict: {idx} packet skipped - interrupt')
            #     continue

            timestamp = self.__calculate_timestamp(packet.cycle_cnt)
            if not self.__within_begin_boundry(timestamp):
                logger.log(
                    logging.DEBUG-4, f'__parse_packets_into_speedscope_dict: {idx} packet skipped - before --begin')
                continue

            if not self.__within_end_boundry(timestamp):
                logger.log(
                    logging.DEBUG-3, f'__parse_packets_into_speedscope_dict: {idx} packet skipped - after --end')
                break

            if not self.__within_fw_boundry(packet.fn):
                logger.log(
                    logging.DEBUG-2, f'__parse_packets_into_speedscope_dict: {idx} packet skipped - not within firmware memory region, {packet.fn:08x}')
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
                logger.error(
                    f'Profile not found: {"0x{:08x}".format(packet.context)}')
                continue
            profile['events'].append(
                {"type": packet.typ, "at": timestamp, "frame": frame_index})
            logger.log(
                logging.DEBUG-5, f"{profile['name']}: {packet.typ} {timestamp:.9f} {frame_index}")

        for profile in profiles:
            # remove all closing events at the beginning
            while len(profile['events']) > 1 and profile['events'][0]['type'] == "C":
                profile['events'].pop(0)

            # remove all events that have zero start time
            while profile and profile['events'][0]['at'] == 0.0:
                profile['events'].pop(0)

        logger.info(f'Profiles parsed: {len(profiles)}')
        for profile in profiles:
            logger.info(
                f"  {profile['name']}: {len(profile['events'])} events")

        shared_frames.append(
            {"name": "OVERFLOW!", "file": "", "line": 0, "col": 1})
        self.overflow_frame_index = len(shared_frames) - 1

        earliest_start = min(
            [profile['events'][0]['at'] for profile in profiles])
        latest_end = max(
            [profile['events'][-1]['at'] for profile in profiles])

        for profile in profiles:
            profile['events'] = self.__fix_events(
                profile, shared_frames)
            # pick the same time range for all threads
            profile['startValue'] = earliest_start
            profile['endValue'] = latest_end

        return {
            "$schema": "https://www.speedscope.app/file-format-schema.json",
            "profiles": profiles,
            "shared": {"frames": shared_frames},
            "exporter": "lukasnee/ucprof",
        }

    def __log_opening_event(self, log_level, context, idx, timestamp, frame, call_stack, frames, suffix=""):
        indent = '  ' * len(call_stack)
        logger.log(log_level,
                   f"{context}|{idx:8d}|{timestamp:.9f}|{indent}{frame['name']}{': ' if suffix else ''}{suffix}")

    def __log_closing_event(self, log_level, context, idx, timestamp, frame, call_stack, frames, suffix=""):
        indent = '  ' * len(call_stack)
        logger.log(log_level,
                   f"{context}|{idx:8d}|{timestamp:.9f}|{indent}~{frame['name']}{': ' if suffix else ''}{suffix}")

    def __fix_events(self, profile, frames):

        # ensure events are in cronological order by finding last chronological sequence and trimming the rest
        last_break_idx = 0
        for idx, event in enumerate(profile['events']):
            if idx == 0:
                continue
            if event['at'] < profile['events'][idx-1]['at']:
                last_break_idx = idx
        profile['events'] = profile['events'][last_break_idx:]

        call_stack = []
        fixed_events = []
        overflow = False
        for idx, event in enumerate(profile['events']):

            if event['type'] == "C":
                # TODO think of better ways to handle broken frames
                # TODO make the breaks more visible in the speedscope GUI
                if not call_stack:
                    self.__log_closing_event(
                        logging.WARNING-1, profile['name'],
                        idx, event['at'], frames[event['frame']], call_stack, frames, "Call stack is empty - skipping")
                    call_stack = []
                    continue
                if call_stack[-1] != event['frame']:
                    logger.log(logging.WARNING-1,
                               f"Call stack inconsistent on {idx} event: tried to close '{frames[event['frame']]['name']}' instead of '{frames[call_stack[-1]]['name']}'")
                    logger.log(
                        logging.INFO-1, "Stack termination (begin)")
                    for frame in reversed(call_stack):
                        fixed_events.append(
                            {"type": "C", "at": profile['events'][idx-1]['at'], "frame": frame})
                        call_stack.pop()
                        self.__log_closing_event(
                            logging.INFO-1, profile['name'], idx, event['at'], frames[frame], call_stack, frames)
                    logger.log(logging.INFO-1, "Stack termination (end)")
                    fixed_events.append(
                        {"type": "O", "at": profile['events'][idx-1]['at'], "frame": self.overflow_frame_index})
                    self.__log_opening_event(
                        logging.INFO-1, profile['name'], idx, event['at'], frames[self.overflow_frame_index], call_stack, frames)
                    overflow = True
                    continue
                fixed_events.append(event)
                call_stack.pop()
                self.__log_closing_event(
                    logging.INFO-1, profile['name'], idx, event['at'], frames[event['frame']], call_stack, frames)
            else:
                if overflow:
                    fixed_events.append(
                        {"type": "C", "at": event['at'], "frame": self.overflow_frame_index})
                    self.__log_closing_event(
                        logging.INFO-1, profile['name'], idx, event['at'], frames[self.overflow_frame_index], call_stack, frames)
                    overflow = False
                self.__log_opening_event(
                    logging.INFO-1, profile['name'], idx, event['at'], frames[event['frame']], call_stack, frames)
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

    def fold_all_stacks(self):
        if not self.args.nm_symbols_path or not self.args.frame_data_path:
            logger.info("Please provide both input file paths.")
            return
        symbols = self.__parse_nm_symbols()
        packets = self.__read_packets_from_file()
        speedscope_dict = self.__parse_packets_into_speedscope_dict(
            symbols, packets)
        filename = f"{self.args.frame_data_path.split('/')[-1].split('.')[0]}.json"
        self.__export_to_json(speedscope_dict, filename)
        logger.info(f"Exported {filename}")


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
    parser.add_argument("--log-level", type=int, default=logging.INFO)
    parser.add_argument("--fw_base", type=int, default=0x24000000)
    parser.add_argument("--fw_size", type=int, default=0x80000)
    parser.add_argument("--no_color", action="store_true")
    parser.add_argument("--top", type=int, default=10,
                        help="Process only the top most eventful threads")
    args = parser.parse_args()
    uc_prof = UcProf(args)
    uc_prof.fold_all_stacks()
