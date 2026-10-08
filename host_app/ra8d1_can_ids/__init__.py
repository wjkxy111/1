"""Shared host-side data layer for RA8D1 edge-AI devices."""

__version__ = "1.1.0"

from .models import (
    BmiTelemetrySnapshot,
    BmiExplanationSnapshot,
    BmiWaveSnapshot,
    CanFrameSnapshot,
    DeviceKind,
    MessageKind,
    ProtocolMessage,
    TelemetrySnapshot,
    device_kind_from_message,
    device_kind_from_name,
)
from .protocol import ProtocolParser, parse_line
from .bmi_demo import BmiDemoSource

__all__ = (
    "BmiTelemetrySnapshot",
    "BmiExplanationSnapshot",
    "BmiWaveSnapshot",
    "BmiDemoSource",
    "CanFrameSnapshot",
    "DeviceKind",
    "MessageKind",
    "ProtocolMessage",
    "ProtocolParser",
    "TelemetrySnapshot",
    "device_kind_from_message",
    "device_kind_from_name",
    "parse_line",
)
