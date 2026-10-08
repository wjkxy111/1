from __future__ import annotations

import unittest
from unittest.mock import patch

from ra8d1_can_ids.demo import DemoSource
from ra8d1_can_ids.models import MessageKind, TelemetrySnapshot
from ra8d1_can_ids.protocol import ProtocolParser


class DemoSourceTests(unittest.TestCase):
    def test_demo_uses_the_public_device_protocol(self) -> None:
        parser = ProtocolParser()
        source = DemoSource()
        messages = [parser.feed_line(line) for line in source.boot_lines()]
        self.assertTrue(all(message.kind not in {MessageKind.INVALID, MessageKind.UNKNOWN}
                            for message in messages))

        lines = source.step()
        messages = [parser.feed_line(line) for line in lines]
        telemetry = next(message for message in messages if message.kind is MessageKind.TELEM)
        frame = next(message for message in messages if message.kind is MessageKind.FRAME)
        self.assertGreaterEqual(TelemetrySnapshot.from_message(telemetry).fps, 0)
        self.assertEqual(8, frame.get_int("DLC"))

    def test_demo_commands_are_parseable_and_stateful(self) -> None:
        parser = ProtocolParser()
        source = DemoSource()
        for command in "lmso cfuieqh".replace(" ", ""):
            with self.subTest(command=command):
                messages = [parser.feed_line(line) for line in source.command(command)]
                self.assertTrue(messages)
                self.assertTrue(all(message.kind not in {MessageKind.INVALID, MessageKind.UNKNOWN}
                                    for message in messages))


if __name__ == "__main__":
    unittest.main()
