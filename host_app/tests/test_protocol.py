from __future__ import annotations

import unittest

from ra8d1_can_ids.models import CanFrameSnapshot, MessageKind, TelemetrySnapshot, reason_labels
from ra8d1_can_ids.protocol import ProtocolParser, parse_line


class ProtocolTests(unittest.TestCase):
    def test_v1_proto_and_telemetry(self) -> None:
        proto = parse_line(
            "PROTO,NAME,RA8D1_CAN_IDS,VERSION,1,TRANSPORT,UART,BAUD,115200\r\n",
            timestamp=12.5,
        )
        self.assertEqual(MessageKind.PROTO, proto.kind)
        self.assertEqual("1", proto.fields["VERSION"])
        self.assertEqual(115200, proto.get_int("BAUD"))
        self.assertEqual(12.5, proto.timestamp)

        line = (
            "TELEM,T_MS,1234,MODE,MONITOR,DEMO,ON,LOOPBACK,OFF,FPS,187,"
            "LOAD_PM,251,IDS,5,SCORE,760,REASON,0x14,TOTAL,999,ANOMALY,3,"
            "UNKNOWN,1,HEALTH,OK,TEC,2,REC,4,DROP,7,BUSOFF,0"
        )
        message = parse_line(line)
        snapshot = TelemetrySnapshot.from_message(message)
        self.assertEqual(MessageKind.TELEM, message.kind)
        self.assertEqual(1234, snapshot.timestamp_ms)
        self.assertTrue(snapshot.demo)
        self.assertFalse(snapshot.loopback)
        self.assertEqual(0x14, snapshot.reason)
        self.assertEqual(("洪泛流量", "载荷跳变"), reason_labels(snapshot.reason))

    def test_v1_frame_and_early_demo_variant(self) -> None:
        line = (
            "FRAME,SEQ,18446744073709551615,T_MS,456,ID,0x18FF50E5,FMT,EXT,FD,ON,BRS,ON,RTR,OFF,"
            "DLC,4,SCORE,900,REASON,0x01,DATA,DEADBEEF"
        )
        message = parse_line(line)
        frame = CanFrameSnapshot.from_message(message)
        self.assertEqual(0x18FF50E5, frame.can_id)
        self.assertTrue(frame.fd)
        self.assertTrue(frame.brs)
        self.assertEqual(18446744073709551615, frame.sequence)
        self.assertEqual(b"\xDE\xAD\xBE\xEF", frame.data)

        # The bundled deterministic demo initially used T_US and omitted RTR.
        legacy = parse_line(
            "FRAME,T_US,9000,ID,0x00000100,FMT,STD,FD,OFF,BRS,OFF,DLC,2,"
            "SCORE,0,REASON,0x00,DATA,1234"
        )
        self.assertEqual(9, CanFrameSnapshot.from_message(legacy).timestamp_ms)

        full_payload = bytes(range(64))
        full = parse_line(
            "FRAME,T_MS,999,ID,0x00000321,FMT,STD,FD,ON,BRS,ON,RTR,OFF,"
            f"DLC,64,SCORE,0,REASON,0x00000000,DATA,{full_payload.hex().upper()}"
        )
        full_frame = CanFrameSnapshot.from_message(full)
        self.assertEqual(64, full_frame.dlc)
        self.assertEqual(full_payload, full_frame.data)

        empty = parse_line(
            "FRAME,T_MS,1000,ID,0x00000100,FMT,STD,FD,OFF,BRS,OFF,RTR,ON,"
            "DLC,0,SCORE,0,REASON,0x00000000,DATA,"
        )
        empty_frame = CanFrameSnapshot.from_message(empty)
        self.assertTrue(empty_frame.rtr)
        self.assertEqual(b"", empty_frame.data)

    def test_sequence_distinguishes_same_millisecond_frames(self) -> None:
        first = CanFrameSnapshot.from_message(parse_line(
            "FRAME,SEQ,40,T_MS,77,ID,0x100,FMT,STD,FD,OFF,BRS,OFF,RTR,OFF,"
            "DLC,1,SCORE,0,REASON,0,DATA,AA"
        ))
        second = CanFrameSnapshot.from_message(parse_line(
            "FRAME,SEQ,41,T_MS,77,ID,0x100,FMT,STD,FD,OFF,BRS,OFF,RTR,OFF,"
            "DLC,1,SCORE,0,REASON,0,DATA,AA"
        ))
        self.assertEqual(first.timestamp_ms, second.timestamp_ms)
        self.assertNotEqual(first.sequence, second.sequence)

    def test_all_existing_firmware_records(self) -> None:
        vectors = {
            "BOOT,RA8D1_CANFD_EDGE_IDS,DISPLAY,READY,CAN,READY,ERR,0,TIMEBASE,READY": MessageKind.BOOT,
            "MODEL,LEARNING,profiles_cleared": MessageKind.MODEL,
            "MODEL,WAITING,no_CAN_frames": MessageKind.MODEL,
            "MODEL,MONITORING,IDS,3,BASE_FPS,160,FLOOD_FPS,320": MessageKind.MODEL,
            "EVENT,T+123,ID,0x00000666,DLC,8,SCORE,650,REASON,0x01": MessageKind.EVENT,
            "DIAG,MODE,MONITOR,DEMO,ON,LOOPBACK,OFF,IDS,3,FPS,160,LOAD_PM,100": MessageKind.DIAG,
            "AI,TOTAL,1000,ANOMALY,2,UNKNOWN,1,BASE_FPS,160,FLOOD_FPS,320": MessageKind.AI,
            "CAN,STATUS,0x80,TEC,0,REC,0,RX,1000,DROP,0,BUSOFF,0,ERR,0x0": MessageKind.CAN,
            "CAN,HEALTH,UNAVAILABLE": MessageKind.CAN,
            "PROFILE,0,ID,0x00000100,STD,DLC,8,N,100,PERIOD_US,10000,RISK,0": MessageKind.PROFILE,
            "LOG,0,T_MS,123,ID,0x00000666,DLC,8,SCORE,650,REASON,0x01": MessageKind.LOG,
            "SELF_TEST,ON": MessageKind.SELF_TEST,
            "LOOPBACK,ON,ERR,0": MessageKind.LOOPBACK,
            "TX,CANFD_BRS,ERR,0": MessageKind.TX,
            "DISPLAY,ERROR,runtime": MessageKind.DISPLAY,
            "COMMAND,UNKNOWN,0x78": MessageKind.COMMAND,
        }
        for line, kind in vectors.items():
            with self.subTest(line=line):
                message = parse_line(line)
                self.assertEqual(kind, message.kind)
                self.assertNotEqual(MessageKind.INVALID, message.kind)

        unavailable = parse_line("CAN,HEALTH,UNAVAILABLE")
        self.assertEqual("UNAVAILABLE", unavailable.fields["HEALTH"])
        event = parse_line(vectors.keys().__iter__().__next__())
        self.assertIsNotNone(event.raw)

    def test_unknown_truncated_and_noise_never_raise(self) -> None:
        parser = ProtocolParser(clock=lambda: 42.0)
        cases: list[str | bytes] = [
            "",
            "TELEM,T_MS",
            "FRAME,T_MS,3,ID",
            "GARBAGE,a,b,c",
            "human readable help",
            b"EVENT,T+2,ID,\xff\xfe",
        ]
        results = [parser.feed_line(case) for case in cases]
        self.assertEqual(MessageKind.INVALID, results[0].kind)
        self.assertEqual(MessageKind.INVALID, results[1].kind)
        self.assertEqual(MessageKind.INVALID, results[2].kind)
        self.assertEqual(MessageKind.UNKNOWN, results[3].kind)
        self.assertEqual(MessageKind.TEXT, results[4].kind)
        self.assertTrue(all(result.timestamp == 42.0 for result in results))


if __name__ == "__main__":
    unittest.main()
