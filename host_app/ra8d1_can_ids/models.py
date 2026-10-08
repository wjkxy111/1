"""Typed, UI-neutral models shared by the RA8D1 edge-AI protocols."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class MessageKind(str, Enum):
    """Record tags emitted by current and protocol-v1 firmware."""

    PROTO = "PROTO"
    BOOT = "BOOT"
    MODEL = "MODEL"
    EVENT = "EVENT"
    DIAG = "DIAG"
    AI = "AI"
    CAN = "CAN"
    PROFILE = "PROFILE"
    LOG = "LOG"
    TX = "TX"
    SELF_TEST = "SELF_TEST"
    LOOPBACK = "LOOPBACK"
    DISPLAY = "DISPLAY"
    COMMAND = "COMMAND"
    TELEM = "TELEM"
    FRAME = "FRAME"
    BMI_TELEM = "BMI_TELEM"
    BMI_WAVE = "BMI_WAVE"
    BMI_EXPLAIN = "BMI_EXPLAIN"
    RESULT = "RESULT"
    FEATURES = "FEATURES"
    TEMP_NOW = "TEMP_NOW"
    BMI088 = "BMI088"
    MONITOR = "MONITOR"
    CALIBRATION = "CALIBRATION"
    BEGIN = "BEGIN"
    TEMP = "TEMP"
    COLUMNS = "COLUMNS"
    DATA = "DATA"
    END = "END"
    ERROR = "ERROR"
    EXPLAIN = "EXPLAIN"
    HELP = "HELP"
    TEXT = "TEXT"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


class DeviceKind(str, Enum):
    """Known firmware families carried by the common UART transport."""

    UNKNOWN = "UNKNOWN"
    CAN_IDS = "RA8D1_CAN_IDS"
    BMI088_EDGE_AI = "RA8D1_BMI088_EDGE_AI"


_DEVICE_NAME_ALIASES: dict[str, DeviceKind] = {
    DeviceKind.CAN_IDS.value: DeviceKind.CAN_IDS,
    "RA8D1_CANFD_EDGE_IDS": DeviceKind.CAN_IDS,
    DeviceKind.BMI088_EDGE_AI.value: DeviceKind.BMI088_EDGE_AI,
    "RA8D1_BMI088_VIBRATION_AI": DeviceKind.BMI088_EDGE_AI,
}


def device_kind_from_name(name: str | None) -> DeviceKind:
    """Map a protocol or legacy boot name to a stable device family."""

    if not name:
        return DeviceKind.UNKNOWN
    normalized = name.strip().upper().replace("-", "_").replace(" ", "_")
    return _DEVICE_NAME_ALIASES.get(normalized, DeviceKind.UNKNOWN)


@dataclass(frozen=True, slots=True)
class ProtocolMessage:
    """One decoded serial line.

    Field values deliberately remain strings so the decoder is forward
    compatible.  ``get_int`` and ``get_bool`` are safe convenience accessors
    for dashboards; malformed or absent values return the supplied default.
    ``timestamp`` is Unix time in seconds at reception.
    """

    kind: MessageKind
    fields: Mapping[str, str] = field(default_factory=dict)
    raw: str = ""
    timestamp: float = 0.0

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.fields.get(key.upper(), default)

    def get_int(self, key: str, default: int | None = None) -> int | None:
        value = self.get(key)
        if value is None:
            return default
        try:
            # base=0 accepts firmware hex fields (0x...) and decimal metrics.
            return int(value.strip(), 0)
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool | None = None) -> bool | None:
        value = self.get(key)
        if value is None:
            return default
        normalized = value.strip().upper()
        if normalized in {"ON", "READY", "OK", "TRUE", "YES", "1"}:
            return True
        if normalized in {"OFF", "ERROR", "FALSE", "NO", "0", "NA"}:
            return False
        return default


def device_kind_from_message(message: ProtocolMessage) -> DeviceKind:
    """Identify a device from identity or family-specific records."""

    if message.kind is MessageKind.PROTO:
        return device_kind_from_name(message.get("NAME"))
    if message.kind is MessageKind.BOOT:
        return device_kind_from_name(message.get("DEVICE"))
    if message.kind is MessageKind.BMI088:
        return DeviceKind.BMI088_EDGE_AI
    if message.kind in {
        MessageKind.BMI_TELEM, MessageKind.BMI_WAVE, MessageKind.BMI_EXPLAIN,
        MessageKind.RESULT, MessageKind.FEATURES, MessageKind.TEMP_NOW,
        MessageKind.EXPLAIN, MessageKind.CALIBRATION, MessageKind.BEGIN,
        MessageKind.TEMP, MessageKind.DATA, MessageKind.END,
    }:
        return DeviceKind.BMI088_EDGE_AI
    if message.kind in {
        MessageKind.TELEM, MessageKind.FRAME, MessageKind.CAN,
        MessageKind.PROFILE, MessageKind.LOG, MessageKind.TX,
    }:
        return DeviceKind.CAN_IDS
    return DeviceKind.UNKNOWN


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    """Frequently used values from a protocol-v1 ``TELEM`` line."""

    timestamp_ms: int = 0
    mode: str = "UNKNOWN"
    demo: bool = False
    loopback: bool = False
    fps: int = 0
    load_permille: int = 0
    learned_ids: int = 0
    score: int = 0
    reason: int = 0
    total: int = 0
    anomaly: int = 0
    unknown: int = 0
    health: str = "NA"
    tec: int = 0
    rec: int = 0
    dropped: int = 0
    bus_off: int = 0

    @classmethod
    def from_message(cls, message: ProtocolMessage) -> "TelemetrySnapshot":
        if message.kind is not MessageKind.TELEM:
            raise ValueError("message is not TELEM")
        number = lambda name: message.get_int(name, 0) or 0
        return cls(
            timestamp_ms=number("T_MS"),
            mode=message.get("MODE", "UNKNOWN") or "UNKNOWN",
            demo=bool(message.get_bool("DEMO", False)),
            loopback=bool(message.get_bool("LOOPBACK", False)),
            fps=number("FPS"),
            load_permille=number("LOAD_PM"),
            learned_ids=number("IDS"),
            score=number("SCORE"),
            reason=number("REASON"),
            total=number("TOTAL"),
            anomaly=number("ANOMALY"),
            unknown=number("UNKNOWN"),
            health=message.get("HEALTH", "NA") or "NA",
            tec=number("TEC"),
            rec=number("REC"),
            dropped=number("DROP"),
            bus_off=number("BUSOFF"),
        )


@dataclass(frozen=True, slots=True)
class CanFrameSnapshot:
    """A latest-frame snapshot emitted in response to the ``q`` command."""

    timestamp_ms: int
    sequence: int | None
    can_id: int
    fmt: str
    fd: bool
    brs: bool
    rtr: bool
    dlc: int
    score: int
    reason: int
    data: bytes

    @classmethod
    def from_message(cls, message: ProtocolMessage) -> "CanFrameSnapshot":
        if message.kind is not MessageKind.FRAME:
            raise ValueError("message is not FRAME")
        payload = message.get("DATA", "") or ""
        try:
            data = bytes.fromhex(payload) if len(payload) % 2 == 0 else b""
        except ValueError:
            data = b""
        number = lambda name: message.get_int(name, 0) or 0
        timestamp_ms = number("T_MS")
        if not timestamp_ms and message.get("T_US") is not None:
            timestamp_ms = number("T_US") // 1000
        return cls(
            timestamp_ms=timestamp_ms,
            sequence=message.get_int("SEQ", None),
            can_id=number("ID"),
            fmt=message.get("FMT", "STD") or "STD",
            fd=bool(message.get_bool("FD", False)),
            brs=bool(message.get_bool("BRS", False)),
            rtr=bool(message.get_bool("RTR", False)),
            dlc=number("DLC"),
            score=number("SCORE"),
            reason=number("REASON"),
            data=data,
        )


@dataclass(frozen=True, slots=True)
class BmiTelemetrySnapshot:
    """Typed values from one ``BMI_TELEM`` inference-window snapshot.

    Firmware uses scaled integers on the wire: temperatures are milli-degrees
    Celsius, confidence is per-mille, and the anomaly score is multiplied by
    100. Unknown fields remain available in :class:`ProtocolMessage` and are
    intentionally ignored here for forward compatibility.
    """

    timestamp_ms: int = 0
    window_id: int = 0
    mode: str = "UNKNOWN"
    monitor: bool = False
    sensor_ready: bool = False
    model: str = "UNKNOWN"
    health: str = "UNKNOWN"
    score_x100: int = 0
    class_name: str = "unknown"
    confidence_permille: int = 0
    temperature_millideg_c: int = 0
    rise_millideg_c: int = 0
    temperature_level: str = "UNKNOWN"
    inference_us: int = 0
    baseline_windows: int = 0
    event_count: int = 0

    @classmethod
    def from_message(cls, message: ProtocolMessage) -> "BmiTelemetrySnapshot":
        if message.kind is not MessageKind.BMI_TELEM:
            raise ValueError("message is not BMI_TELEM")

        def number(*names: str, default: int = 0) -> int:
            for name in names:
                if message.get(name) is not None:
                    return message.get_int(name, default) or 0
            return default

        def text(*names: str, default: str) -> str:
            for name in names:
                value = message.get(name)
                if value is not None:
                    return value
            return default

        return cls(
            timestamp_ms=number("T_MS", "TIMESTAMP_MS"),
            window_id=number("WINDOW", "WINDOW_ID"),
            mode=text("MODE", default="UNKNOWN"),
            monitor=bool(message.get_bool("MONITOR", False)),
            sensor_ready=bool(message.get_bool("SENSOR", False)),
            model=text("MODEL", "MODEL_STATE", default="UNKNOWN"),
            health=text("HEALTH", default="UNKNOWN"),
            score_x100=number("SCORE_X100", "SCORE"),
            class_name=text("CLASS", "CLASS_NAME", default="unknown"),
            confidence_permille=number("CONF_PM", "CONFIDENCE_PM", "CONFIDENCE_PER_MILLE"),
            temperature_millideg_c=number("TEMP_MC", "TEMP_MILLI_C", "TEMPERATURE_MC"),
            rise_millideg_c=number("RISE_MC", "TEMP_RISE_MC", "TEMPERATURE_RISE_MC"),
            temperature_level=text("TEMP_LEVEL", "TEMPERATURE_LEVEL", default="UNKNOWN"),
            inference_us=number("INFER_US", "INFERENCE_US"),
            baseline_windows=number("BASE_WINDOWS", "BASELINE_WINDOWS"),
            event_count=number("EVENTS", "EVENT_COUNT"),
        )

    @property
    def temperature_c(self) -> float:
        return self.temperature_millideg_c / 1000.0

    @property
    def rise_c(self) -> float:
        return self.rise_millideg_c / 1000.0

    @classmethod
    def from_result(cls, message: ProtocolMessage) -> "BmiTelemetrySnapshot":
        """Adapt one legacy positional ``RESULT`` inference record."""

        if message.kind is not MessageKind.RESULT:
            raise ValueError("message is not RESULT")
        number = lambda name: message.get_int(name, 0) or 0
        return cls(
            window_id=number("WINDOW"),
            mode="MONITOR",
            monitor=True,
            sensor_ready=True,
            model=message.get("MODEL", "UNKNOWN") or "UNKNOWN",
            health=message.get("HEALTH", "UNKNOWN") or "UNKNOWN",
            score_x100=number("SCORE_X100"),
            class_name=message.get("CLASS", "unknown") or "unknown",
            confidence_permille=number("CONF_PM"),
            temperature_millideg_c=number("TEMP_MC"),
            rise_millideg_c=number("RISE_MC"),
            temperature_level=message.get("TEMP_LEVEL", "UNKNOWN") or "UNKNOWN",
            inference_us=number("INFER_US"),
        )


@dataclass(frozen=True, slots=True)
class BmiWaveSnapshot:
    """Signed 8-bit downsampled vibration waveform from ``BMI_WAVE``."""

    window_id: int = 0
    encoding: str = "UNKNOWN"
    declared_points: int = 0
    points: tuple[int, ...] = ()
    valid: bool = False

    @classmethod
    def from_message(cls, message: ProtocolMessage) -> "BmiWaveSnapshot":
        if message.kind is not MessageKind.BMI_WAVE:
            raise ValueError("message is not BMI_WAVE")
        window_id = message.get_int("WINDOW", 0) or 0
        encoding = (message.get("ENC", "UNKNOWN") or "UNKNOWN").upper()
        declared = message.get_int("POINTS", 0) or 0
        payload = (message.get("DATA", "") or "").strip()
        raw = b""
        if encoding == "S8HEX" and len(payload) % 2 == 0:
            try:
                raw = bytes.fromhex(payload)
            except ValueError:
                raw = b""
        points = tuple(value if value < 128 else value - 256 for value in raw)
        valid = encoding == "S8HEX" and declared == 64 and len(points) == 64
        return cls(window_id, encoding, declared, points, valid)


@dataclass(frozen=True, slots=True)
class BmiExplanationSnapshot:
    """One ranked explainability item emitted after an inference window."""

    window_id: int = 0
    rank: int = 0
    feature: str = "unknown"
    contribution_x100: int = 0

    @classmethod
    def from_message(cls, message: ProtocolMessage) -> "BmiExplanationSnapshot":
        if message.kind is not MessageKind.BMI_EXPLAIN:
            raise ValueError("message is not BMI_EXPLAIN")
        return cls(
            window_id=message.get_int("WINDOW", 0) or 0,
            rank=message.get_int("RANK", 0) or 0,
            feature=message.get("FEATURE", "unknown") or "unknown",
            contribution_x100=message.get_int("CONTRIB_X100", 0) or 0,
        )


REASON_LABELS: dict[int, str] = {
    0x01: "未知 ID",
    0x02: "周期异常",
    0x04: "洪泛流量",
    0x08: "DLC 变化",
    0x10: "载荷跳变",
    0x20: "总线故障",
    0x40: "模型已满",
}


def reason_labels(mask: int) -> tuple[str, ...]:
    """Return all human-readable labels present in the firmware UI mask."""

    return tuple(label for bit, label in REASON_LABELS.items() if mask & bit)
