"""Session capture, CSV export and deterministic JSONL replay."""

from __future__ import annotations

import csv
import json
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import TextIO

from .models import MessageKind, ProtocolMessage


# Keep the original identifier readable while accepting both edge-AI projects.
# Existing JSONL captures remain fully compatible because the loader does not
# reject older format labels.
SESSION_FORMAT = "ra8d1-edge-ai-session-v1"


def _message_to_dict(message: ProtocolMessage) -> dict[str, object]:
    return {
        "format": SESSION_FORMAT,
        "timestamp": message.timestamp,
        "kind": message.kind.value,
        "fields": dict(message.fields),
        "raw": message.raw,
    }


def _message_from_dict(value: object) -> ProtocolMessage | None:
    if not isinstance(value, dict):
        return None
    try:
        raw_kind = str(value.get("kind", "UNKNOWN")).upper()
        try:
            kind = MessageKind(raw_kind)
        except ValueError:
            kind = MessageKind.UNKNOWN
        raw_fields = value.get("fields", {})
        fields = ({str(key).upper(): str(item) for key, item in raw_fields.items()}
                  if isinstance(raw_fields, dict) else {})
        raw = str(value.get("raw", ""))
        timestamp = float(value.get("timestamp", 0.0))
        return ProtocolMessage(kind, fields, raw, timestamp)
    except (TypeError, ValueError, OverflowError):
        return None


class SessionRecorder:
    """Thread-safe in-memory capture with optional streaming JSONL storage."""

    def __init__(self, max_records: int = 250_000) -> None:
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = int(max_records)
        self._records: list[ProtocolMessage] = []
        self._lock = threading.RLock()
        self._active = False
        self._stream: TextIO | None = None
        self._stream_path: Path | None = None
        self.dropped_records = 0

    @property
    def recording(self) -> bool:
        with self._lock:
            return self._active

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._records)

    @property
    def path(self) -> Path | None:
        with self._lock:
            return self._stream_path

    def start(self, path: str | Path | None = None, *, clear: bool = True) -> None:
        """Begin capture and optionally stream every message to a UTF-8 JSONL file."""

        with self._lock:
            self._close_stream()
            if clear:
                self._records.clear()
                self.dropped_records = 0
            self._stream_path = Path(path).expanduser().resolve() if path is not None else None
            if self._stream_path is not None:
                self._stream_path.parent.mkdir(parents=True, exist_ok=True)
                self._stream = self._stream_path.open("w", encoding="utf-8", newline="\n")
            self._active = True

    def stop(self) -> None:
        with self._lock:
            self._active = False
            self._close_stream()

    close = stop

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self.dropped_records = 0

    def ingest(self, message: ProtocolMessage) -> bool:
        """Capture one protocol message; return false when recording is stopped."""

        if not isinstance(message, ProtocolMessage):
            raise TypeError("message must be ProtocolMessage")
        with self._lock:
            if not self._active:
                return False
            if len(self._records) >= self.max_records:
                # Bound RAM while retaining the newest view.  The optional
                # JSONL stream still preserves the complete on-disk session.
                del self._records[0]
                self.dropped_records += 1
            self._records.append(message)
            if self._stream is not None:
                self._stream.write(json.dumps(
                    _message_to_dict(message), ensure_ascii=False, separators=(",", ":")
                ))
                self._stream.write("\n")
                self._stream.flush()
            return True

    record = ingest

    def ingest_event(self, event: object) -> bool:
        """Capture ``LinkEvent.message`` without importing the transport module."""

        message = getattr(event, "message", None)
        return self.ingest(message) if isinstance(message, ProtocolMessage) else False

    def snapshot(self, kind: MessageKind | str | None = None) -> list[ProtocolMessage]:
        with self._lock:
            records = list(self._records)
        if kind is None:
            return records
        selected = kind if isinstance(kind, MessageKind) else MessageKind(str(kind).upper())
        return [message for message in records if message.kind is selected]

    def save_jsonl(self, path: str | Path) -> Path:
        """Write the current in-memory window as portable session JSONL."""

        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        records = self.snapshot()
        with destination.open("w", encoding="utf-8", newline="\n") as output:
            for message in records:
                output.write(json.dumps(
                    _message_to_dict(message), ensure_ascii=False, separators=(",", ":")
                ))
                output.write("\n")
        return destination

    def export_csv(
        self,
        path: str | Path,
        *,
        kinds: Iterable[MessageKind | str] | None = None,
    ) -> Path:
        """Export one rectangular CSV, retaining raw text and every seen field."""

        records = self.snapshot()
        if kinds is not None:
            accepted = {value if isinstance(value, MessageKind)
                        else MessageKind(str(value).upper()) for value in kinds}
            records = [message for message in records if message.kind in accepted]
        field_names = sorted({key for message in records for key in message.fields})
        headers = ["timestamp", "kind", "raw", *field_names]
        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for message in records:
                row: dict[str, object] = {
                    "timestamp": f"{message.timestamp:.6f}",
                    "kind": message.kind.value,
                    "raw": message.raw,
                }
                row.update(message.fields)
                writer.writerow(row)
        return destination

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.flush()
            self._stream.close()
            self._stream = None

    def __enter__(self) -> "SessionRecorder":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()


def load_jsonl(path: str | Path) -> list[ProtocolMessage]:
    """Load valid records from JSONL; malformed/truncated lines are skipped."""

    records: list[ProtocolMessage] = []
    with Path(path).expanduser().open("r", encoding="utf-8-sig") as source:
        for line in source:
            try:
                value = json.loads(line)
            except (json.JSONDecodeError, UnicodeError):
                continue
            message = _message_from_dict(value)
            if message is not None:
                records.append(message)
    return records


class SessionReplay:
    """Replay stored messages in order, optionally preserving capture timing."""

    def __init__(self, records: Iterable[ProtocolMessage]) -> None:
        self.records = tuple(records)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "SessionReplay":
        return cls(load_jsonl(path))

    def __iter__(self) -> Iterator[ProtocolMessage]:
        return iter(self.records)

    def play(
        self,
        callback: Callable[[ProtocolMessage], object],
        *,
        speed: float = 1.0,
        stop_event: threading.Event | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> int:
        """Deliver records to ``callback``; ``speed=0`` disables all delays."""

        if speed < 0:
            raise ValueError("speed must be non-negative")
        delivered = 0
        previous: float | None = None
        for message in self.records:
            if stop_event is not None and stop_event.is_set():
                break
            if speed > 0 and previous is not None:
                delay = max(0.0, message.timestamp - previous) / speed
                if delay > 0:
                    if stop_event is not None and sleep is time.sleep:
                        if stop_event.wait(delay):
                            break
                    else:
                        sleep(delay)
            callback(message)
            delivered += 1
            previous = message.timestamp
        return delivered
