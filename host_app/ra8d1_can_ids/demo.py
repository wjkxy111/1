"""Deterministic no-hardware demo source using the real device text protocol."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
import time


@dataclass
class _DemoFrame:
    can_id: int
    dlc: int
    period_us: int
    flags: int = 0


class DemoSource:
    """Generate realistic RA8D1 telemetry for portfolio demos and UI testing."""

    def __init__(self) -> None:
        self._rng = random.Random(0x8D1)
        self._frames = (
            _DemoFrame(0x100, 8, 10_000),
            _DemoFrame(0x120, 8, 20_000),
            _DemoFrame(0x180, 16, 50_000, 0x06),
            _DemoFrame(0x220, 8, 100_000),
            _DemoFrame(0x321, 32, 200_000, 0x06),
        )
        self.reset()

    def reset(self) -> None:
        self.started = time.monotonic()
        self.last_step = self.started
        self.total = 0
        self.anomalies = 0
        self.unknown = 0
        self.dropped = 0
        self.bus_off = 0
        self.mode = "LEARNING"
        self.attack_demo = True
        self.loopback = False
        self.frame_index = 0
        self.event_index = 0
        self._last_event_second = -1
        self._history: list[str] = []

    def boot_lines(self) -> list[str]:
        lines = [
            "PROTO,RA8D1_CAN_IDS,1",
            "BOOT,RA8D1_CANFD_EDGE_IDS,DISPLAY,OK,CAN,OK,ERR,0,TIMEBASE,OK",
            "MODEL,LEARNING,profiles_cleared",
            "SELF_TEST,ON",
        ]
        lines.extend(self._profile_lines())
        return lines

    def step(self) -> list[str]:
        """Advance the scenario and return zero or more protocol lines."""

        now = time.monotonic()
        elapsed = now - self.started
        delta = max(0.02, now - self.last_step)
        self.last_step = now
        if elapsed >= 4.0 and self.mode == "LEARNING":
            self.mode = "MONITORING"
            transition = ["MODEL,MONITORING,IDS,5,BASE_FPS,187,FLOOD_FPS,374"]
        else:
            transition = []

        fps = int(185 + (18 * math.sin(elapsed * 0.9)) + self._rng.randint(-4, 4))
        if self.attack_demo and (10.0 < (elapsed % 26.0) < 15.0):
            fps += 210
        self.total += max(1, int(fps * delta))
        load = max(20, min(970, int(105 + (fps * 0.78))))

        reason = 0
        score = max(0, int(26 + 18 * math.sin(elapsed * 1.6)))
        can_id = self._frames[self.frame_index % len(self._frames)].can_id
        dlc = self._frames[self.frame_index % len(self._frames)].dlc
        flags = self._frames[self.frame_index % len(self._frames)].flags
        phase = elapsed % 26.0
        if self.mode == "MONITORING" and self.attack_demo:
            if 7.0 <= phase < 8.4:
                reason, score, can_id, dlc = 0x01, 910, 0x6A5, 8
            elif 10.0 <= phase < 12.4:
                reason, score = 0x04, 760
            elif 15.0 <= phase < 16.5:
                reason, score, dlc = 0x08, 820, 4
            elif 19.0 <= phase < 20.8:
                reason, score = 0x12, 875

        whole_second = int(elapsed)
        event_line: list[str] = []
        if reason and whole_second != self._last_event_second:
            self._last_event_second = whole_second
            self.anomalies += 1
            if reason & 0x01:
                self.unknown += 1
            event = (f"EVENT,T+{int(elapsed * 1000)},ID,0x{can_id:08X},DLC,{dlc},"
                     f"SCORE,{score},REASON,0x{reason:02X}")
            event_line.append(event)
            self._history.append(event)
            self._history = self._history[-16:]

        frame = self._make_frame_line(elapsed, can_id, dlc, flags, score, reason)
        telemetry = (
            f"TELEM,T_MS,{int(elapsed * 1000)},MODE,{self.mode},DEMO,"
            f"{'ON' if self.attack_demo else 'OFF'},LOOPBACK,{'ON' if self.loopback else 'OFF'},"
            f"FPS,{fps},LOAD_PM,{load},IDS,5,SCORE,{score},REASON,0x{reason:02X},"
            f"TOTAL,{self.total},ANOMALY,{self.anomalies},UNKNOWN,{self.unknown},"
            f"TEC,0,REC,0,RX,{self.total},DROP,{self.dropped},BUSOFF,{self.bus_off}"
        )
        self.frame_index += 1
        return transition + [telemetry, frame] + event_line

    def command(self, command: str) -> list[str]:
        command = command.strip().lower()[:1]
        if command == "l":
            self.mode = "LEARNING"
            self.started = time.monotonic()
            self.anomalies = 0
            self.unknown = 0
            self._history.clear()
            return ["MODEL,LEARNING,profiles_cleared"]
        if command == "m":
            self.mode = "MONITORING"
            return ["MODEL,MONITORING,IDS,5,BASE_FPS,187,FLOOD_FPS,374"]
        if command == "s":
            self.attack_demo = not self.attack_demo
            return [f"SELF_TEST,{'ON' if self.attack_demo else 'OFF'}"]
        if command == "o":
            self.loopback = not self.loopback
            return [f"LOOPBACK,{'ON' if self.loopback else 'OFF'},ERR,0"]
        if command == "c":
            return ["TX,CLASSIC,ERR,0"]
        if command == "f":
            return ["TX,CANFD_BRS,ERR,0"]
        if command == "i":
            return self._diagnostic_lines()
        if command == "e":
            return self._profile_lines() + self._log_lines()
        if command == "q":
            return self.step()
        if command == "u":
            return ["DISPLAY,PAGE,NEXT"]
        if command == "h":
            return ["HELP,l,m,s,o,c,f,u,i,e,q,h"]
        return [f"COMMAND,UNKNOWN,0x{ord(command or '?'):02X}"]

    def _make_frame_line(self, elapsed: float, can_id: int, dlc: int, flags: int,
                         score: int, reason: int) -> str:
        payload = bytes(((can_id + self.frame_index + index * 13) & 0xFF) for index in range(dlc))
        fmt = "EXT" if flags & 0x01 else "STD"
        fd = "ON" if flags & 0x02 else "OFF"
        brs = "ON" if flags & 0x04 else "OFF"
        return (f"FRAME,SEQ,{self.frame_index + 1},T_US,{int(elapsed * 1_000_000)},ID,0x{can_id:08X},FMT,{fmt},FD,{fd},BRS,{brs},"
                f"DLC,{dlc},SCORE,{score},REASON,0x{reason:02X},DATA,{payload.hex().upper()}")

    def _diagnostic_lines(self) -> list[str]:
        elapsed = int((time.monotonic() - self.started) * 1000)
        return [
            f"DIAG,MODE,{self.mode},DEMO,{'ON' if self.attack_demo else 'OFF'},"
            f"LOOPBACK,{'ON' if self.loopback else 'OFF'},IDS,5,FPS,187,LOAD_PM,251",
            f"AI,TOTAL,{self.total},ANOMALY,{self.anomalies},UNKNOWN,{self.unknown},"
            "BASE_FPS,187,FLOOD_FPS,374",
            f"CAN,STATUS,0x00000000,TEC,0,REC,0,RX,{self.total},DROP,{self.dropped},"
            f"BUSOFF,{self.bus_off},ERR,0x00000000",
        ]

    def _profile_lines(self) -> list[str]:
        lines: list[str] = []
        for index, frame in enumerate(self._frames):
            rate_x10 = int(10_000_000 / frame.period_us)
            lines.append(
                f"PROFILE,{index},ID,0x{frame.can_id:08X},{'EXT' if frame.flags & 1 else 'STD'},"
                f"DLC,{frame.dlc},N,{1200 - index * 137},PERIOD_US,{frame.period_us},RISK,{12 + index * 7},"
                f"RATE_X10,{rate_x10}"
            )
        return lines

    def _log_lines(self) -> list[str]:
        if not self._history:
            return []
        output: list[str] = []
        for index, event in enumerate(reversed(self._history)):
            tokens = event.split(",")
            fields = {tokens[pos]: tokens[pos + 1] for pos in range(2, len(tokens) - 1, 2)}
            timestamp_ms = tokens[1][2:] if len(tokens) > 1 and tokens[1].startswith("T+") else "0"
            output.append(
                f"LOG,{index},T_MS,{timestamp_ms},ID,{fields.get('ID', '0x0')},"
                f"DLC,{fields.get('DLC', '0')},SCORE,{fields.get('SCORE', '0')},"
                f"REASON,{fields.get('REASON', '0x00')}"
            )
        return output
