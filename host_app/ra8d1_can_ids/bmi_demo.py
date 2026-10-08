"""Deterministic no-hardware source for the BMI088 edge-AI protocol."""

from __future__ import annotations

from collections.abc import Callable
import math
import time


class BmiDemoSource:
    """Generate repeatable BMI088 telemetry using the real UART vocabulary.

    Supplying a controllable ``clock`` makes every line byte-for-byte
    repeatable in tests. With the default monotonic clock the source is ready
    for a GUI timer: call :meth:`step` two to five times per second.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.reset()

    def reset(self) -> None:
        self._started = self._clock()
        self._window_id = 0
        self._monitor = True
        self._calibrating = True
        self._baseline_windows = 0
        self._event_count = 0
        self._last_health = "OK"
        self._last_temperature = 28_600

    def boot_lines(self) -> list[str]:
        return [
            "PROTO,NAME,RA8D1_BMI088_EDGE_AI,VERSION,1,TRANSPORT,UART,BAUD,115200",
            "BOOT,RA8D1_BMI088_EDGE_AI,SENSOR,READY,DISPLAY,READY,MODEL,ONE_CLASS_FALLBACK",
            "CALIBRATION,START,keep_machine_in_normal_state",
        ]

    def step(self) -> list[str]:
        elapsed = max(0.0, self._clock() - self._started)
        transition: list[str] = []
        if self._calibrating:
            expected = min(16, int(elapsed * 8.0))
            if expected > self._baseline_windows:
                self._baseline_windows = expected
                transition.append(f"CALIBRATION,{self._baseline_windows},16")
            if self._baseline_windows >= 16:
                self._calibrating = False
                transition.append("CALIBRATION,DONE,TEMP_BASELINE,28600")

        self._window_id += 1
        timestamp_ms = int(elapsed * 1000.0)
        temperature = 28_600 + int(380.0 * math.sin(elapsed * 0.31))
        rise = temperature - 28_600
        mode = "CALIBRATE" if self._calibrating else ("MONITOR" if self._monitor else "IDLE")

        score, class_name, confidence, health = 115, "anomaly_only", 0, "OK"
        scenario = "normal"
        temperature_level = "NORMAL"
        if not self._calibrating and self._monitor:
            cycle = int(max(0.0, elapsed - 2.0)) % 24
            if 6 <= cycle < 10:
                score, health, scenario = 1180, "ALARM", "imbalance-like"
            elif 13 <= cycle < 16:
                score, health, scenario = 970, "WARN", "bearing-band"
            elif 19 <= cycle < 22:
                score, scenario = 330, "thermal"
                temperature = 62_400
                rise = 33_800
                temperature_level, health = "WARN", "WARN"

            if health != self._last_health:
                self._event_count += 1
                transition.append(
                    f"EVENT,T+{timestamp_ms},TYPE,MACHINE_HEALTH,WINDOW,{self._window_id},"
                    f"FROM,{self._last_health},TO,{health},CLASS,{class_name},"
                    f"SCORE_X100,{score},DETAIL,{scenario}"
                )
                self._last_health = health

        self._last_temperature = temperature

        telemetry = (
            f"BMI_TELEM,T_MS,{timestamp_ms},WINDOW,{self._window_id},MODE,{mode},"
            f"MONITOR,{'ON' if self._monitor else 'OFF'},SENSOR,READY,"
            f"MODEL,ONE_CLASS_FALLBACK,HEALTH,{health},SCORE_X100,{score},"
            f"CLASS,{class_name},CONF_PM,{confidence},TEMP_MC,{temperature},"
            f"RISE_MC,{rise},TEMP_LEVEL,{temperature_level},INFER_US,{34 + self._window_id % 7},"
            f"BASE_WINDOWS,{self._baseline_windows},EVENTS,{self._event_count}"
        )
        waveform = tuple(max(-128, min(127, int(
            68.0 * math.sin((point / 64.0) * math.tau * 3.0 + elapsed)
            + 17.0 * math.sin((point / 64.0) * math.tau * 7.0)
        ))) for point in range(64))
        encoded = "".join(f"{value & 0xFF:02X}" for value in waveform)
        wave_line = (
            f"BMI_WAVE,WINDOW,{self._window_id},ENC,S8HEX,POINTS,64,DATA,{encoded}"
        )
        explanations = self._explanation_lines(scenario)
        spectral = {
            "normal": (0.08, 0.12, 0.18, 0.10, 0.07, 0.05, 0.04, 0.03, 0.02, 0.02, 0.01, 0.01),
            "imbalance-like": (0.12, 0.95, 0.61, 0.24, 0.13, 0.08, 0.06, 0.04, 0.03, 0.02, 0.02, 0.01),
            "bearing-band": (0.05, 0.07, 0.10, 0.12, 0.14, 0.20, 0.31, 0.56, 0.93, 0.72, 0.55, 0.30),
            "thermal": (0.07, 0.10, 0.15, 0.09, 0.06, 0.04, 0.03, 0.02, 0.02, 0.01, 0.01, 0.01),
        }[scenario]
        feature_values = [
            0.042, 0.039, 0.061, 0.083, 0.129, 1.55, 4.70, 0.029,
            31.0, 28.0, 44.0, 87.0, *spectral,
            temperature / 1000.0, rise / 1000.0,
        ]
        feature_line = (f"FEATURES,{self._window_id}," +
                        ",".join(str(round(value * 1_000_000)) for value in feature_values))
        return transition + [telemetry, wave_line, feature_line, *explanations]

    def command(self, command: str) -> list[str]:
        normalized = command.strip().lower()[:1]
        if normalized == "q":
            return self.step()
        if normalized == "b":
            self._started = self._clock()
            self._calibrating = True
            self._baseline_windows = 0
            return ["CALIBRATION,START,keep_machine_in_normal_state"]
        if normalized == "m":
            self._monitor = not self._monitor
            return [f"MONITOR,{'ON' if self._monitor else 'OFF'}"]
        if normalized == "t":
            return [f"TEMP_NOW,{self._last_temperature},28600,{self._last_temperature - 28600},NORMAL"]
        if normalized == "p":
            values = [int((0.02 + (index * 0.003)) * 1_000_000) for index in range(26)]
            return [f"FEATURES,{self._window_id}," + ",".join(str(value) for value in values)]
        if normalized in "01234":
            label = int(normalized)
            return [
                f"BEGIN,{self._window_id},{label},800,512",
                f"TEMP,{self._window_id},{self._last_temperature},"
                f"{self._last_temperature - 28600},NORMAL",
                f"END,{self._window_id}",
            ]
        if normalized == "i":
            return [
                "DIAG,MODEL,ONE_CLASS_FALLBACK,VERSION,vib-temp-1.1,SCHEMA,edge-ai/1,"
                f"BASELINE_WINDOWS,{self._baseline_windows},INFERENCE_US,{34 + self._window_id % 7},"
                "HEALTH,OK"
            ]
        if normalized == "u":
            return ["DISPLAY,PAGE,NEXT"]
        if normalized == "h":
            return ["HELP,0,1,2,3,4,b,m,p,t,u,i,q,h"]
        return [f"COMMAND,UNKNOWN,0x{ord(normalized or '?'):02X}"]

    def _explanation_lines(self, scenario: str) -> list[str]:
        feature_sets = {
            "imbalance-like": (("acc_x_rms_g", 510), ("spec_25", 330), ("gyro_z_rms_dps", 205)),
            "bearing-band": (("acc_kurtosis", 470), ("acc_crest", 318), ("spec_250", 188)),
            "thermal": (("temperature_rise_c", 430), ("temperature_c", 380), ("acc_mag_rms_g", 41)),
            "normal": (("acc_mag_rms_g", 91), ("gyro_peak_dps", 62), ("temperature_c", 21)),
        }
        selected = feature_sets.get(scenario, feature_sets["normal"])
        return [
            f"BMI_EXPLAIN,WINDOW,{self._window_id},RANK,{rank},FEATURE,{feature},"
            f"CONTRIB_X100,{contribution}"
            for rank, (feature, contribution) in enumerate(selected, start=1)
        ]
