from __future__ import annotations

import unittest

from ra8d1_can_ids.bmi_demo import BmiDemoSource
from ra8d1_can_ids.models import (
    BmiExplanationSnapshot,
    BmiTelemetrySnapshot,
    BmiWaveSnapshot,
    DeviceKind,
    MessageKind,
    device_kind_from_message,
    device_kind_from_name,
)
from ra8d1_can_ids.protocol import ProtocolParser, parse_line


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class MultiDeviceProtocolTests(unittest.TestCase):
    def test_device_identity_from_v1_and_legacy_declarations(self) -> None:
        parser = ProtocolParser(clock=lambda: 1.0)
        can_proto = parser.feed_line("PROTO,RA8D1_CAN_IDS,1")
        self.assertEqual(DeviceKind.CAN_IDS, parser.device_kind)
        self.assertEqual("1", parser.protocol_version)
        self.assertEqual(DeviceKind.CAN_IDS, device_kind_from_message(can_proto))

        parser.reset_identity()
        self.assertEqual(DeviceKind.UNKNOWN, parser.device_kind)
        bmi_proto = parser.feed_line(
            "PROTO,NAME,RA8D1_BMI088_EDGE_AI,VERSION,1,TRANSPORT,UART,BAUD,115200"
        )
        self.assertEqual(DeviceKind.BMI088_EDGE_AI, parser.device_kind)
        self.assertEqual("RA8D1_BMI088_EDGE_AI", parser.protocol_name)
        self.assertEqual(DeviceKind.BMI088_EDGE_AI, device_kind_from_message(bmi_proto))

        boot = parse_line("BOOT,RA8D1_CANFD_EDGE_IDS,DISPLAY,READY")
        self.assertEqual(DeviceKind.CAN_IDS, device_kind_from_message(boot))
        self.assertEqual(DeviceKind.BMI088_EDGE_AI,
                         device_kind_from_name("ra8d1-bmi088-vibration-ai"))
        self.assertEqual(DeviceKind.UNKNOWN, device_kind_from_name("future-board"))

        parser.reset_identity()
        parser.feed_line("BMI_WAVE,WINDOW,1,ENC,S8HEX,POINTS,64,DATA," + ("00" * 64))
        self.assertEqual(DeviceKind.BMI088_EDGE_AI, parser.device_kind)
        parser.reset_identity()
        parser.feed_line("FRAME,T_MS,1,ID,0x100,FMT,STD,FD,OFF,BRS,OFF,RTR,OFF,DLC,0,SCORE,0,REASON,0,DATA,")
        self.assertEqual(DeviceKind.CAN_IDS, parser.device_kind)

    def test_bmi_telemetry_typed_snapshot_and_unknown_fields(self) -> None:
        line = (
            "BMI_TELEM,T_MS,1250,WINDOW,17,MODE,MONITOR,MONITOR,ON,SENSOR,READY,"
            "MODEL,ONE_CLASS_FALLBACK,HEALTH,WARN,SCORE_X100,975,CLASS,bearing,"
            "CONF_PM,872,TEMP_MC,62400,RISE_MC,-2800,TEMP_LEVEL,WARN,INFER_US,41,"
            "BASE_WINDOWS,16,EVENTS,3,FUTURE_FIELD,kept"
        )
        message = parse_line(line)
        snapshot = BmiTelemetrySnapshot.from_message(message)
        self.assertEqual(MessageKind.BMI_TELEM, message.kind)
        self.assertEqual("kept", message.get("FUTURE_FIELD"))
        self.assertEqual(17, snapshot.window_id)
        self.assertTrue(snapshot.monitor)
        self.assertTrue(snapshot.sensor_ready)
        self.assertEqual("bearing", snapshot.class_name)
        self.assertEqual(975, snapshot.score_x100)
        self.assertEqual(62.4, snapshot.temperature_c)
        self.assertEqual(-2.8, snapshot.rise_c)

        aliases = parse_line(
            "BMI_TELEM,TIMESTAMP_MS,2,WINDOW_ID,3,MODE,IDLE,MONITOR,OFF,SENSOR,ERROR,"
            "MODEL_STATE,NOT_TRAINED,HEALTH,SENSOR,SCORE,9,CLASS_NAME,unknown,"
            "CONFIDENCE_PER_MILLE,4,TEMPERATURE_MC,-1000,TEMP_RISE_MC,-2000,"
            "TEMPERATURE_LEVEL,NORMAL,INFERENCE_US,7,BASELINE_WINDOWS,1,EVENT_COUNT,2"
        )
        adapted = BmiTelemetrySnapshot.from_message(aliases)
        self.assertFalse(adapted.monitor)
        self.assertFalse(adapted.sensor_ready)
        self.assertEqual(-1000, adapted.temperature_millideg_c)
        self.assertEqual(2, adapted.event_count)

    def test_wave_and_explanation_snapshots_are_safe(self) -> None:
        encoded = "00807FFF" + ("00" * 60)
        wave = BmiWaveSnapshot.from_message(parse_line(
            f"BMI_WAVE,WINDOW,9,ENC,S8HEX,POINTS,64,DATA,{encoded},FUTURE,x"
        ))
        self.assertTrue(wave.valid)
        self.assertEqual((0, -128, 127, -1), wave.points[:4])
        self.assertEqual(64, len(wave.points))

        malformed = BmiWaveSnapshot.from_message(parse_line(
            "BMI_WAVE,WINDOW,9,ENC,S8HEX,POINTS,64,DATA,XX"
        ))
        self.assertFalse(malformed.valid)
        self.assertEqual((), malformed.points)

        explanation = BmiExplanationSnapshot.from_message(parse_line(
            "BMI_EXPLAIN,WINDOW,9,RANK,1,FEATURE,acc_z_kurtosis,CONTRIB_X100,470"
        ))
        self.assertEqual(1, explanation.rank)
        self.assertEqual("acc_z_kurtosis", explanation.feature)

    def test_legacy_bmi_positional_records(self) -> None:
        result = parse_line(
            "RESULT,42,1180,imbalance,914,30600,2000,NORMAL,ALARM,37,vib-temp-1.1"
        )
        snapshot = BmiTelemetrySnapshot.from_result(result)
        self.assertEqual(MessageKind.RESULT, result.kind)
        self.assertEqual(42, snapshot.window_id)
        self.assertEqual("imbalance", snapshot.class_name)
        self.assertEqual("vib-temp-1.1", snapshot.model)

        temperature = parse_line("TEMP_NOW,30125,28600,1525,NORMAL")
        self.assertEqual(MessageKind.TEMP_NOW, temperature.kind)
        self.assertEqual(30125, temperature.get_int("TEMP_MC"))

        values = ",".join(str(index * 1000) for index in range(26))
        features = parse_line(f"FEATURES,42,{values}")
        self.assertEqual(MessageKind.FEATURES, features.kind)
        self.assertEqual(26, features.get_int("COUNT"))
        self.assertEqual("25000", features.get("F25"))
        self.assertEqual(MessageKind.INVALID, parse_line("FEATURES,42,1,2").kind)

    def test_legacy_capture_and_control_records(self) -> None:
        parser = ProtocolParser()
        records = (
            "BMI088,INIT,0,ACC_ID,0x1E,GYRO_ID,0x0F",
            "DISPLAY,ST7796U,READY,256x480,RGB565",
            "MONITOR,ON",
            "CALIBRATION,7,16",
            "BEGIN,42,3,800,512",
            "TEMP,42,30125,1525,NORMAL",
            "COLUMNS,window,label,sample,ax,ay,az,gx,gy,gz",
            "DATA,42,3,0,1,2,3,4,5,6",
            "END,42",
            "ERROR,TEMPERATURE_READ",
        )
        messages = [parser.feed_line(line) for line in records]
        self.assertTrue(all(item.kind not in {MessageKind.INVALID, MessageKind.UNKNOWN}
                            for item in messages))
        self.assertEqual(DeviceKind.BMI088_EDGE_AI, parser.device_kind)
        self.assertEqual(7, messages[3].get_int("CURRENT"))
        self.assertEqual(512, messages[4].get_int("SAMPLES"))
        self.assertEqual(6, messages[7].get_int("GZ"))

    def test_family_specific_records_identify_device_without_proto(self) -> None:
        parser = ProtocolParser()
        result = parser.feed_line(
            "RESULT,2,100,anomaly_only,0,29000,400,NORMAL,OK,35,vib-temp-1.1"
        )
        self.assertEqual(DeviceKind.BMI088_EDGE_AI, device_kind_from_message(result))
        self.assertEqual(DeviceKind.BMI088_EDGE_AI, parser.device_kind)

        parser.reset_identity()
        frame = parser.feed_line(
            "FRAME,SEQ,1,T_US,10,ID,0x100,FMT,STD,FD,OFF,BRS,OFF,DLC,1,"
            "SCORE,0,REASON,0,DATA,00"
        )
        self.assertEqual(DeviceKind.CAN_IDS, device_kind_from_message(frame))
        self.assertEqual(DeviceKind.CAN_IDS, parser.device_kind)

        explanation = parse_line("EXPLAIN,1,acc_z_kurtosis,470")
        self.assertEqual(MessageKind.EXPLAIN, explanation.kind)
        self.assertEqual("acc_z_kurtosis", explanation.get("FEATURE"))
        self.assertEqual(470, explanation.get_int("CONTRIB_X100"))

    def test_deterministic_demo_emits_parseable_current_protocol(self) -> None:
        clock_a = _Clock()
        clock_b = _Clock()
        demo_a = BmiDemoSource(clock_a)
        demo_b = BmiDemoSource(clock_b)
        self.assertEqual(demo_a.boot_lines(), demo_b.boot_lines())
        clock_a.value = clock_b.value = 3.5
        lines_a = demo_a.step()
        lines_b = demo_b.step()
        self.assertEqual(lines_a, lines_b)

        messages = [parse_line(line) for line in demo_a.boot_lines() + lines_a]
        self.assertNotIn(MessageKind.INVALID, {message.kind for message in messages})
        telemetry = next(message for message in messages if message.kind is MessageKind.BMI_TELEM)
        wave = next(message for message in messages if message.kind is MessageKind.BMI_WAVE)
        explanations = [message for message in messages if message.kind is MessageKind.BMI_EXPLAIN]
        self.assertEqual(16, BmiTelemetrySnapshot.from_message(telemetry).baseline_windows)
        self.assertEqual(64, len(BmiWaveSnapshot.from_message(wave).points))
        self.assertEqual(3, len(explanations))


if __name__ == "__main__":
    unittest.main()
