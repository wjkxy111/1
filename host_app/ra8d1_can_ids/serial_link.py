"""Threaded pyserial transport with a queue-only UI boundary."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
import re

from .models import MessageKind, ProtocolMessage
from .protocol import ProtocolParser

try:
    import serial
    from serial import SerialException
except ImportError:  # Keep protocol/demo imports usable before optional install.
    serial = None  # type: ignore[assignment]

    class SerialException(OSError):
        pass


@dataclass(frozen=True, slots=True)
class LinkEvent:
    """One item delivered from the worker to the UI thread."""

    type: str  # "message", "connected", "disconnected" or "error"
    message: ProtocolMessage | None = None
    detail: str = ""
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class SerialPortInfo:
    """Small, stable view of a pySerial port discovery record."""

    device: str
    description: str = ""
    hwid: str = ""
    vid: int | None = None
    pid: int | None = None

    @property
    def display_name(self) -> str:
        description = self.description.strip()
        if not description or description.lower() in {"n/a", self.device.lower()}:
            return self.device
        return f"{self.device} · {description}"


def _natural_port_key(device: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"(?i)(COM)(\d+)", device.strip())
    if match:
        return (match.group(1).upper(), int(match.group(2)), "")
    return (device.upper(), -1, device)


def preferred_serial_port(ports: list[SerialPortInfo], current: str = "") -> str | None:
    """Choose a likely USB-UART while preserving an existing valid choice.

    This function only selects a combobox value; it never opens a port.  USB
    bridges and debug probes rank ahead of Bluetooth/virtual modem ports.
    """

    if not ports:
        return None
    current_upper = current.strip().upper()
    for port in ports:
        if port.device.upper() == current_upper:
            return port.device

    def score(port: SerialPortInfo) -> tuple[int, tuple[str, int, str]]:
        haystack = f"{port.description} {port.hwid}".lower()
        value = 0
        if port.vid is not None and port.pid is not None:
            value += 40
        if any(token in haystack for token in (
            "usb serial", "usb-serial", "ch340", "ch341", "cp210", "ftdi",
            "xds110", "j-link", "jlink", "segger", "uart bridge", "wch.cn",
        )):
            value += 35
        # SEGGER's USB vendor ID; the RA8D1 on-board J-Link CDC observed on
        # the target machine is VID 1366 / PID 1024 (hexadecimal).
        if port.vid == 0x1366:
            value += 45
        elif "usb" in haystack:
            value += 15
        if any(token in haystack for token in ("bluetooth", "rfcomm", "modem")):
            value -= 80
        # The natural key is only a deterministic tiebreaker; COM10 therefore
        # sorts after COM9 instead of between COM1 and COM2.
        return value, _natural_port_key(port.device)

    return max(ports, key=score).device


class SerialLink:
    """Read lines in a worker thread and expose them via :class:`queue.Queue`.

    ``serial_for_url`` is used deliberately, so hardware ports and pyserial's
    ``loop://`` test port share exactly the same implementation.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        *,
        timeout: float = 0.1,
        write_timeout: float = 1.0,
        queue_size: int = 4096,
        parser: ProtocolParser | None = None,
    ) -> None:
        self.port = port
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)
        self.write_timeout = float(write_timeout)
        self.events: queue.Queue[LinkEvent] = queue.Queue(maxsize=queue_size)
        self._parser = parser or ProtocolParser()
        self._serial = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._dropped_events = 0

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive() and not self._stop.is_set())

    @property
    def is_open(self) -> bool:
        device = self._serial
        return bool(device is not None and getattr(device, "is_open", False))

    @property
    def dropped_events(self) -> int:
        return self._dropped_events

    def start(self) -> None:
        """Open the port and start the reader.  Safe to call more than once."""

        if serial is None:
            raise RuntimeError("pyserial is required: python -m pip install pyserial")
        with self._state_lock:
            if self.is_running:
                return
            self._stop.clear()
            try:
                self._serial = serial.serial_for_url(
                    self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout,
                    write_timeout=self.write_timeout,
                    do_not_open=False,
                )
            except Exception as error:
                self._emit(LinkEvent("error", detail=str(error), timestamp=time.time()))
                raise
            self._thread = threading.Thread(
                target=self._reader_loop,
                name="ra8d1-serial-reader",
                daemon=True,
            )
            self._thread.start()
        self._emit(LinkEvent("connected", detail=self.port, timestamp=time.time()))

    # Conventional aliases make integration with Tk applications less brittle.
    open = start

    def stop(self, join_timeout: float = 1.0) -> None:
        """Stop the reader and close the serial handle; safe and idempotent."""

        self._stop.set()
        device = self._serial
        if device is not None:
            try:
                device.cancel_read()
            except (AttributeError, OSError, SerialException):
                pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(max(0.0, join_timeout))
        with self._state_lock:
            device = self._serial
            self._serial = None
            self._thread = None
            if device is not None:
                try:
                    device.close()
                except (OSError, SerialException):
                    pass
        self._emit(LinkEvent("disconnected", detail=self.port, timestamp=time.time()))

    close = stop

    def send(self, data: str | bytes) -> None:
        """Write raw data atomically; raises when the link is not open."""

        payload = data.encode("ascii") if isinstance(data, str) else bytes(data)
        device = self._serial
        if device is None or not getattr(device, "is_open", False):
            raise RuntimeError("serial link is not open")
        with self._write_lock:
            device.write(payload)
            device.flush()

    def send_command(self, command: str, *, newline: bool = False) -> None:
        """Send one firmware command byte (optionally followed by CR/LF)."""

        normalized = command.strip()
        if len(normalized) != 1 or not normalized.isascii():
            raise ValueError("firmware command must be one ASCII character")
        suffix = "\r\n" if newline else ""
        self.send(normalized.encode("ascii") + suffix.encode("ascii"))

    def get_event(self, timeout: float | None = None) -> LinkEvent:
        return self.events.get(timeout=timeout)

    def drain_events(self, limit: int | None = None) -> list[LinkEvent]:
        """Non-blockingly return at most ``limit`` queued :class:`LinkEvent`s."""

        drained: list[LinkEvent] = []
        maximum = limit if limit is not None and limit >= 0 else None
        while maximum is None or len(drained) < maximum:
            try:
                drained.append(self.events.get_nowait())
            except queue.Empty:
                break
        return drained

    def drain_messages(self, limit: int | None = None) -> list[ProtocolMessage]:
        """Convenience view of message-type events for simple consumers."""

        return [event.message for event in self.drain_events(limit)
                if event.type == "message" and event.message is not None]

    def _reader_loop(self) -> None:
        failure = ""
        while not self._stop.is_set():
            device = self._serial
            if device is None:
                break
            try:
                payload = device.readline()
                if not payload:
                    continue
                message = self._parser.feed_line(payload)
                self._emit(LinkEvent("message", message=message, timestamp=message.timestamp))
            except (OSError, SerialException) as error:
                if not self._stop.is_set():
                    failure = str(error)
                    self._emit(LinkEvent("error", detail=failure, timestamp=time.time()))
                break
            except Exception as error:  # Do not silently kill the reader thread.
                failure = f"{type(error).__name__}: {error}"
                self._emit(LinkEvent("error", detail=failure, timestamp=time.time()))
        if failure:
            self._stop.set()

    def _emit(self, event: LinkEvent) -> None:
        try:
            self.events.put_nowait(event)
        except queue.Full:
            # Favor current telemetry over stale data while remaining bounded.
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            try:
                self.events.put_nowait(event)
            except queue.Full:
                pass
            self._dropped_events += 1


def list_serial_port_info() -> list[SerialPortInfo]:
    """Return sorted port metadata, or an empty list without pyserial."""

    if serial is None:
        return []
    from serial.tools import list_ports

    discovered = [
        SerialPortInfo(
            device=str(port.device),
            description=str(getattr(port, "description", "") or ""),
            hwid=str(getattr(port, "hwid", "") or ""),
            vid=getattr(port, "vid", None),
            pid=getattr(port, "pid", None),
        )
        for port in list_ports.comports()
    ]
    return sorted(discovered, key=lambda item: _natural_port_key(item.device))


def list_serial_ports() -> list[str]:
    """Compatibility view returning only stable device names."""

    return [port.device for port in list_serial_port_info()]
