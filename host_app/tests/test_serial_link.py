from __future__ import annotations

import time
import unittest

from ra8d1_can_ids.models import MessageKind
from ra8d1_can_ids.serial_link import SerialLink, SerialPortInfo, preferred_serial_port


class SerialLinkTests(unittest.TestCase):
    def test_preferred_port_preserves_choice_and_prefers_usb_uart(self) -> None:
        ports = [
            SerialPortInfo("COM3", "Standard Serial over Bluetooth link", "BTHENUM"),
            SerialPortInfo("COM12", "USB-SERIAL CH340", "USB VID:PID=1A86:7523", 0x1A86, 0x7523),
            SerialPortInfo("COM4", "Communications Port", "ACPI"),
        ]
        self.assertEqual("COM12", preferred_serial_port(ports))
        self.assertEqual("COM4", preferred_serial_port(ports, "com4"))
        self.assertIsNone(preferred_serial_port([]))

    def test_preferred_port_recognizes_ra8d1_jlink_cdc_vid(self) -> None:
        ports = [
            SerialPortInfo("COM7", "USB Serial Device", "USB", 0x1234, 0x0001),
            SerialPortInfo("COM16", "J-Link CDC UART Port", "USB VID:PID=1366:1024",
                           0x1366, 0x1024),
        ]
        self.assertEqual("COM16", preferred_serial_port(ports))

    def test_loop_url_thread_queue_and_command(self) -> None:
        link = SerialLink("loop://", timeout=0.02)
        try:
            link.start()
            link.send("TELEM,T_MS,7,MODE,LEARN\r\n")
            deadline = time.monotonic() + 1.0
            messages = []
            while time.monotonic() < deadline and not messages:
                messages.extend(link.drain_messages())
                time.sleep(0.01)
            self.assertTrue(messages)
            self.assertEqual(MessageKind.TELEM, messages[0].kind)
            self.assertEqual(7, messages[0].get_int("T_MS"))

            link.send_command("q", newline=True)
            deadline = time.monotonic() + 1.0
            text = None
            while time.monotonic() < deadline and text is None:
                for event in link.drain_events():
                    if event.message is not None:
                        text = event.message
                time.sleep(0.01)
            self.assertIsNotNone(text)
            self.assertEqual("q", text.raw)
        finally:
            link.stop()
        self.assertFalse(link.is_open)

    def test_invalid_command_and_idempotent_stop(self) -> None:
        link = SerialLink("loop://")
        with self.assertRaises(ValueError):
            link.send_command("query")
        with self.assertRaises(RuntimeError):
            link.send_command("q")
        link.stop()
        link.stop()


if __name__ == "__main__":
    unittest.main()
