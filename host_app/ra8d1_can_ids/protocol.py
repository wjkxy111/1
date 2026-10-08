"""Fault-tolerant parser for the common RA8D1 edge-AI UART envelope."""

from __future__ import annotations

import time
from collections.abc import Callable

from .models import DeviceKind, MessageKind, ProtocolMessage, device_kind_from_message


_KINDS = {kind.value: kind for kind in MessageKind if kind not in {
    MessageKind.TEXT, MessageKind.UNKNOWN, MessageKind.INVALID
}}


def _pairs(tokens: list[str], start: int) -> tuple[dict[str, str], bool]:
    fields: dict[str, str] = {}
    tail = tokens[start:]
    complete = (len(tail) % 2) == 0
    for index in range(0, len(tail) - 1, 2):
        key = tail[index].strip().upper()
        if key:
            fields[key] = tail[index + 1].strip()
    return fields, complete


class ProtocolParser:
    """Parse one CR/LF-delimited line at a time without raising on input data."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._device_kind = DeviceKind.UNKNOWN
        self._protocol_name = ""
        self._protocol_version = ""

    @property
    def device_kind(self) -> DeviceKind:
        """Last recognized device family in this serial stream."""

        return self._device_kind

    @property
    def protocol_name(self) -> str:
        return self._protocol_name

    @property
    def protocol_version(self) -> str:
        return self._protocol_version

    def reset_identity(self) -> None:
        """Forget identity metadata before reusing a parser for another port."""

        self._device_kind = DeviceKind.UNKNOWN
        self._protocol_name = ""
        self._protocol_version = ""

    def feed_line(
        self,
        line: str | bytes,
        *,
        timestamp: float | None = None,
    ) -> ProtocolMessage:
        received = self._clock() if timestamp is None else float(timestamp)
        if isinstance(line, bytes):
            raw = line.decode("utf-8", errors="replace")
        elif isinstance(line, str):
            raw = line
        else:
            raw = str(line)
        raw = raw.rstrip("\r\n")
        stripped = raw.strip()
        if not stripped:
            return ProtocolMessage(MessageKind.INVALID, {"ERROR": "empty"}, raw, received)

        tokens = [token.strip() for token in stripped.split(",")]
        tag = tokens[0].upper()
        kind = _KINDS.get(tag)
        if kind is None:
            if len(tokens) == 1:
                return ProtocolMessage(MessageKind.TEXT, {"TEXT": stripped}, raw, received)
            return ProtocolMessage(
                MessageKind.UNKNOWN,
                {"TAG": tokens[0], "TOKENS": str(max(0, len(tokens) - 1))},
                raw,
                received,
            )

        try:
            fields, complete = self._decode(kind, tokens)
        except Exception as error:  # Parser is an isolation boundary for serial noise.
            return ProtocolMessage(
                MessageKind.INVALID,
                {"TAG": tag, "ERROR": type(error).__name__},
                raw,
                received,
            )
        if not complete:
            fields["_ERROR"] = "incomplete"
            fields["_KIND"] = kind.value
            return ProtocolMessage(MessageKind.INVALID, fields, raw, received)
        message = ProtocolMessage(kind, fields, raw, received)
        self._observe_identity(message)
        return message

    parse_line = feed_line

    def _observe_identity(self, message: ProtocolMessage) -> None:
        identified = device_kind_from_message(message)
        if identified is DeviceKind.UNKNOWN:
            if message.kind in {
                MessageKind.BMI_TELEM,
                MessageKind.BMI_WAVE,
                MessageKind.BMI_EXPLAIN,
                MessageKind.RESULT,
                MessageKind.FEATURES,
                MessageKind.TEMP_NOW,
                MessageKind.EXPLAIN,
                MessageKind.BMI088,
                MessageKind.MONITOR,
                MessageKind.CALIBRATION,
                MessageKind.BEGIN,
                MessageKind.TEMP,
                MessageKind.DATA,
                MessageKind.END,
            }:
                identified = DeviceKind.BMI088_EDGE_AI
            elif message.kind in {
                MessageKind.TELEM,
                MessageKind.FRAME,
                MessageKind.CAN,
                MessageKind.PROFILE,
                MessageKind.LOG,
                MessageKind.TX,
            }:
                identified = DeviceKind.CAN_IDS
        if identified is not DeviceKind.UNKNOWN:
            self._device_kind = identified
        if message.kind is MessageKind.PROTO:
            self._protocol_name = message.get("NAME", "") or ""
            self._protocol_version = message.get("VERSION", "") or ""

    @staticmethod
    def _decode(kind: MessageKind, tokens: list[str]) -> tuple[dict[str, str], bool]:
        if kind is MessageKind.PROTO:
            if len(tokens) == 3 and tokens[1].upper() != "NAME":
                return {"NAME": tokens[1], "VERSION": tokens[2]}, True
            return _pairs(tokens, 1)

        if kind is MessageKind.BOOT:
            if len(tokens) < 2:
                return {}, False
            fields, complete = _pairs(tokens, 2)
            fields["DEVICE"] = tokens[1]
            return fields, complete

        if kind is MessageKind.MODEL:
            if len(tokens) < 2:
                return {}, False
            fields: dict[str, str] = {"STATE": tokens[1]}
            if len(tokens) == 3:
                fields["DETAIL"] = tokens[2]
                return fields, True
            extra, complete = _pairs(tokens, 2)
            fields.update(extra)
            return fields, complete

        if kind is MessageKind.EVENT:
            if len(tokens) < 2:
                return {}, False
            if tokens[1].upper().startswith("T+"):
                fields, complete = _pairs(tokens, 2)
                fields["T_MS"] = tokens[1][2:]
                fields["T+"] = tokens[1][2:]
                return fields, complete
            return _pairs(tokens, 1)

        if kind is MessageKind.PROFILE:
            if len(tokens) < 5:
                return {}, False
            fields: dict[str, str] = {"INDEX": tokens[1]}
            # Legacy firmware places STD/EXT after the ID value without a key.
            if tokens[2].upper() == "ID":
                fields["ID"] = tokens[3]
                fields["FMT"] = tokens[4]
                extra, complete = _pairs(tokens, 5)
                fields.update(extra)
                return fields, complete
            return fields, False

        if kind is MessageKind.RESULT:
            # Legacy BMI088 firmware positional result:
            # window, score_x100, class, confidence_pm, temp_mc, rise_mc,
            # temperature_level, health, inference_us, model version.
            names = (
                "WINDOW", "SCORE_X100", "CLASS", "CONF_PM", "TEMP_MC",
                "RISE_MC", "TEMP_LEVEL", "HEALTH", "INFER_US", "MODEL",
            )
            values = tokens[1:]
            return dict(zip(names, values, strict=False)), len(values) == len(names)

        if kind is MessageKind.TEMP_NOW:
            names = ("TEMP_MC", "BASELINE_MC", "RISE_MC", "TEMP_LEVEL")
            values = tokens[1:]
            return dict(zip(names, values, strict=False)), len(values) == len(names)

        if kind is MessageKind.BMI088:
            if len(tokens) < 3:
                return {}, False
            fields = {"STATE": tokens[1], "RESULT": tokens[2]}
            extra, complete = _pairs(tokens, 3)
            fields.update(extra)
            return fields, complete

        if kind is MessageKind.MONITOR:
            return ({"STATE": tokens[1]}, True) if len(tokens) == 2 else ({}, False)

        if kind is MessageKind.CALIBRATION:
            if len(tokens) < 2:
                return {}, False
            state = tokens[1].upper()
            if state == "START":
                return {"STATE": state, "DETAIL": ",".join(tokens[2:])}, True
            if state == "DONE":
                fields = {"STATE": state}
                extra, complete = _pairs(tokens, 2)
                fields.update(extra)
                return fields, complete
            if len(tokens) == 3:
                return {"STATE": "PROGRESS", "CURRENT": tokens[1], "TOTAL": tokens[2]}, True
            return {}, False

        if kind is MessageKind.BEGIN:
            names = ("WINDOW", "LABEL", "RATE_HZ", "SAMPLES")
            values = tokens[1:]
            return dict(zip(names, values, strict=False)), len(values) == len(names)

        if kind is MessageKind.TEMP:
            names = ("WINDOW", "TEMP_MC", "RISE_MC", "TEMP_LEVEL")
            values = tokens[1:]
            return dict(zip(names, values, strict=False)), len(values) == len(names)

        if kind is MessageKind.DATA:
            names = ("WINDOW", "LABEL", "SAMPLE", "AX", "AY", "AZ", "GX", "GY", "GZ")
            values = tokens[1:]
            return dict(zip(names, values, strict=False)), len(values) == len(names)

        if kind is MessageKind.END:
            return ({"WINDOW": tokens[1]}, True) if len(tokens) == 2 else ({}, False)

        if kind is MessageKind.COLUMNS:
            return {"NAMES": ",".join(tokens[1:])}, len(tokens) > 1

        if kind is MessageKind.ERROR:
            return {"SOURCE": tokens[1] if len(tokens) > 1 else "UNKNOWN",
                    "DETAIL": ",".join(tokens[2:])}, len(tokens) > 1

        if kind is MessageKind.EXPLAIN:
            names = ("RANK", "FEATURE", "CONTRIB_X100")
            values = tokens[1:]
            return dict(zip(names, values, strict=False)), len(values) == len(names)

        if kind is MessageKind.FEATURES:
            if len(tokens) < 2:
                return {}, False
            values = tokens[2:]
            fields = {"WINDOW": tokens[1], "COUNT": str(len(values))}
            fields.update({f"F{index}": value for index, value in enumerate(values)})
            # Existing BMI088 schema has exactly 26 scaled feature values.
            return fields, len(values) == 26

        if kind is MessageKind.LOG:
            if len(tokens) < 2:
                return {}, False
            fields, complete = _pairs(tokens, 2)
            fields["INDEX"] = tokens[1]
            return fields, complete

        if kind in {MessageKind.SELF_TEST, MessageKind.LOOPBACK}:
            if len(tokens) < 2:
                return {}, False
            fields = {"STATE": tokens[1]}
            extra, complete = _pairs(tokens, 2)
            fields.update(extra)
            return fields, complete

        if kind is MessageKind.TX:
            if len(tokens) < 2:
                return {}, False
            fields = {"TYPE": tokens[1]}
            extra, complete = _pairs(tokens, 2)
            fields.update(extra)
            return fields, complete

        if kind is MessageKind.COMMAND:
            if len(tokens) < 2:
                return {}, False
            fields = {"STATE": tokens[1]}
            if len(tokens) >= 3:
                fields["VALUE"] = tokens[2]
            return fields, len(tokens) <= 3

        if kind is MessageKind.DISPLAY and len(tokens) >= 2:
            # Both projects retain positional legacy display diagnostics.
            return {"DRIVER": tokens[1], "STATE": tokens[2] if len(tokens) >= 3 else "UNKNOWN",
                    "DETAIL": ",".join(tokens[3:])}, True

        if kind is MessageKind.HELP:
            return {"COMMANDS": ",".join(tokens[1:])}, len(tokens) > 1

        # DIAG, AI, CAN, TELEM, FRAME, BMI_TELEM, BMI_WAVE and BMI_EXPLAIN
        # are key/value records.
        # Keeping values as strings makes future firmware fields automatically
        # usable while typed snapshots consume only fields they know.
        return _pairs(tokens, 1)


def parse_line(line: str | bytes, *, timestamp: float | None = None) -> ProtocolMessage:
    """Stateless convenience wrapper used by tests and log importers."""

    return ProtocolParser().feed_line(line, timestamp=timestamp)
