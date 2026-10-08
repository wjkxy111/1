"""BMI088 vibration/temperature edge-AI dashboard for the unified host app.

The component owns only its notebook pages and display state.  Serial I/O,
protocol parsing and device selection stay in :mod:`ra8d1_can_ids.app`, which
can hide or restore these pages through :attr:`tab_specs`.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
import time
import tkinter as tk
from tkinter import messagebox, ttk
from collections.abc import Callable

from .models import (
    BmiExplanationSnapshot,
    BmiTelemetrySnapshot,
    BmiWaveSnapshot,
    MessageKind,
    ProtocolMessage,
)
from .widgets import (
    BmiTrendChart,
    COLORS,
    ExplanationBars,
    MetricCard,
    ScoreGauge,
    SpectrumBars,
    WaveformChart,
)


# Keep this order synchronized with vibration_features.c.  FEATURES values are
# transported as feature * 1e6 so integers remain deterministic across tools.
FEATURE_NAMES: tuple[str, ...] = (
    "acc_x_rms_g",
    "acc_y_rms_g",
    "acc_z_rms_g",
    "acc_mag_rms_g",
    "acc_mag_peak_g",
    "acc_crest",
    "acc_kurtosis",
    "acc_delta_rms_g",
    "gyro_x_rms_dps",
    "gyro_y_rms_dps",
    "gyro_z_rms_dps",
    "gyro_peak_dps",
    "spec_12p5",
    "spec_25",
    "spec_50",
    "spec_75",
    "spec_100",
    "spec_125",
    "spec_150",
    "spec_200",
    "spec_250",
    "spec_300",
    "spec_350",
    "spec_390",
    "temperature_c",
    "temperature_rise_c",
)


FEATURE_UNITS: tuple[str, ...] = (
    "g", "g", "g", "g", "g", "比值", "比值", "g",
    "°/s", "°/s", "°/s", "°/s",
    "相对谱值", "相对谱值", "相对谱值", "相对谱值", "相对谱值", "相对谱值",
    "相对谱值", "相对谱值", "相对谱值", "相对谱值", "相对谱值", "相对谱值",
    "°C", "°C",
)


FEATURE_LABELS: tuple[str, ...] = (
    "加速度 X 轴 RMS",
    "加速度 Y 轴 RMS",
    "加速度 Z 轴 RMS",
    "合加速度 RMS",
    "合加速度峰值",
    "加速度峰值因子",
    "加速度峭度",
    "加速度变化量 RMS",
    "角速度 X 轴 RMS",
    "角速度 Y 轴 RMS",
    "角速度 Z 轴 RMS",
    "角速度峰值",
    "12.5 Hz 频带",
    "25 Hz 频带",
    "50 Hz 频带",
    "75 Hz 频带",
    "100 Hz 频带",
    "125 Hz 频带",
    "150 Hz 频带",
    "200 Hz 频带",
    "250 Hz 频带",
    "300 Hz 频带",
    "350 Hz 频带",
    "390 Hz 频带",
    "当前温度",
    "相对基线温升",
)


FEATURE_DISPLAY_NAMES = dict(zip(FEATURE_NAMES, FEATURE_LABELS, strict=True))

CLASS_LABELS: dict[str, str] = {
    "normal": "正常",
    "imbalance": "不平衡",
    "loose": "松动",
    "rub": "摩擦",
    "bearing": "轴承故障",
    "anomaly_only": "仅异常检测",
    "unknown": "未知",
}

HEALTH_LABELS: dict[str, str] = {
    "OK": "正常",
    "WARN": "预警",
    "ALARM": "报警",
    "SENSOR": "传感器故障",
    "ERROR": "错误",
    "UNKNOWN": "未知",
    "START": "启动",
    "DEVICE": "设备",
    "EVENT": "事件",
}

MODE_LABELS: dict[str, str] = {
    "IDLE": "空闲",
    "MONITOR": "连续监测",
    "CALIBRATE": "基线校准",
    "CAPTURE": "样本采集",
    "UNKNOWN": "未知",
}

TEMPERATURE_LABELS: dict[str, str] = {
    "OK": "正常",
    "NORMAL": "正常",
    "WARN": "温度预警",
    "ALARM": "温度报警",
    "ERROR": "温度异常",
    "UNKNOWN": "未知",
}


MODEL_DESCRIPTIONS: dict[str, str] = {
    "TRAINED": (
        "TRAINED：设备端训练模型已就绪，类别与置信度均来自 RA8D1 本地推理。"
    ),
    "ONE_CLASS_FALLBACK": (
        "ONE_CLASS_FALLBACK：异常由 26 维特征相对正常基线的偏离度判定；"
        "当前只输出 anomaly_only，不提供故障子类和五分类概率。"
    ),
    "NOT_TRAINED": (
        "NOT_TRAINED：模型尚未就绪，请在安全、稳定的正常工况下执行 b 校准。"
    ),
    "UNKNOWN": "等待设备上报模型状态。",
}


class FusionStatusChart(tk.Canvas):
    """Compact graphical view of the three inputs to the health decision."""

    def __init__(self, master: tk.Misc, **kwargs: object) -> None:
        kwargs.setdefault("height", 154)
        kwargs.setdefault("background", COLORS["surface"])
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)
        self._score_x100 = 0
        self._temperature_mc = 0
        self._rise_mc = 0
        self._health = "UNKNOWN"
        self._sensor_ready = False
        self.bind("<Configure>", lambda _event: self._draw())

    def clear(self) -> None:
        self.set_state(0, 0, 0, "UNKNOWN", False)

    def set_state(
        self,
        score_x100: int,
        temperature_mc: int,
        rise_mc: int,
        health: str,
        sensor_ready: bool,
    ) -> None:
        self._score_x100 = score_x100
        self._temperature_mc = temperature_mc
        self._rise_mc = rise_mc
        self._health = health.strip().upper() or "UNKNOWN"
        self._sensor_ready = sensor_ready
        self._draw()

    @staticmethod
    def _risk_color(value: float, warning: float, alarm: float) -> str:
        if value >= alarm:
            return COLORS["red"]
        if value >= warning:
            return COLORS["amber"]
        return COLORS["green"]

    def _draw(self) -> None:
        self.delete("all")
        width = max(260, self.winfo_width())
        title_font = ("Microsoft YaHei UI", 8, "bold")
        body_font = ("Microsoft YaHei UI", 7)
        value_font = ("Microsoft YaHei UI", 7, "bold")

        self.create_text(8, 8, text="多源健康融合", anchor="nw", fill=COLORS["muted"],
                         font=title_font)
        health_text = HEALTH_LABELS.get(self._health, self._health)
        badge_color = BmiDashboard._health_color(self._health)
        badge_width = max(60, 18 + len(health_text) * 13)
        self.create_rectangle(width - badge_width - 8, 6, width - 8, 29,
                              fill=badge_color, outline="")
        self.create_text(width - badge_width / 2 - 8, 17, text=health_text,
                         fill="#07111F", font=title_font)

        rows = (
            ("振动分数", self._score_x100 / 100.0, 7.0, 9.0, 12.0,
             f"{self._score_x100 / 100.0:.2f}"),
            ("当前温度", self._temperature_mc / 1000.0, 60.0, 70.0, 85.0,
             f"{self._temperature_mc / 1000.0:.1f} °C"),
            ("相对温升", max(0.0, self._rise_mc / 1000.0), 15.0, 25.0, 35.0,
             f"{self._rise_mc / 1000.0:+.1f} °C"),
        )
        bar_left = 77
        bar_right = max(bar_left + 70, width - 74)
        for row, (label, value, warning, alarm, scale_max, display) in enumerate(rows):
            y = 47 + row * 31
            self.create_text(8, y, text=label, anchor="w", fill=COLORS["text"],
                             font=body_font)
            self.create_rectangle(bar_left, y - 6, bar_right, y + 6,
                                  fill=COLORS["surface_alt"], outline=COLORS["border"])
            ratio = min(1.0, max(0.0, value / scale_max))
            color = self._risk_color(value, warning, alarm)
            if ratio > 0:
                self.create_rectangle(bar_left + 1, y - 5,
                                      bar_left + (bar_right - bar_left) * ratio, y + 5,
                                      fill=color, outline="")
            self.create_text(width - 8, y, text=display, anchor="e", fill=color,
                             font=value_font)
        if not self._sensor_ready:
            self.create_text(8, 142, text="等待 BMI088 有效数据", anchor="sw",
                             fill=COLORS["purple"], font=body_font)
        else:
            self.create_text(8, 142, text="阈值：振动 7/9 · 温度 60/70 °C · 温升 15/25 °C",
                             anchor="sw", fill=COLORS["muted"], font=body_font)


class BmiDashboard:
    """Four-page BMI088 workbench embedded in a shared ``ttk.Notebook``.

    Parameters
    ----------
    notebook:
        Notebook that receives the four dashboard frames immediately.
    send_command:
        UI-thread callback accepting one firmware command (``b/m/p/t/u/i`` or
        the labelled capture commands ``0..4``).
    export_callback:
        Optional no-argument callback owned by the host application.
    """

    SCORE_ALARM_X100 = 900
    SCORE_GAUGE_ALARM = 700
    MAX_EVENTS = 600

    def __init__(
        self,
        notebook: ttk.Notebook,
        send_command: Callable[[str], object],
        export_callback: Callable[[], object] | None = None,
    ) -> None:
        self.notebook = notebook
        self.send_command = send_command
        self.export_callback = export_callback

        self.frames: dict[str, ttk.Frame] = {
            "health": ttk.Frame(notebook, padding=(10, 8)),
            "waveform": ttk.Frame(notebook, padding=(10, 8)),
            "features": ttk.Frame(notebook, padding=(10, 8)),
            "events": ttk.Frame(notebook, padding=(10, 8)),
        }
        self.tab_specs: tuple[tuple[ttk.Frame, str], ...] = (
            (self.frames["health"], "机器健康"),
            (self.frames["waveform"], "波形与频谱"),
            (self.frames["features"], "特征与解释"),
            (self.frames["events"], "健康事件"),
        )
        for frame, title in self.tab_specs:
            self.notebook.add(frame, text=title)

        self._last_window_id: int | None = None
        self._last_health: str | None = None
        self._latest_snapshot: BmiTelemetrySnapshot | None = None
        self._wave_window: int | None = None
        self._explanation_window: int | None = None
        self._explanations: dict[int, tuple[str, int]] = {}
        self._event_keys: set[tuple[object, ...]] = set()
        self._event_key_order: deque[tuple[object, ...]] = deque()
        self._event_rows: deque[tuple[str, ...]] = deque(maxlen=self.MAX_EVENTS)

        self._build_health_page()
        self._build_waveform_page()
        self._build_features_page()
        self._build_events_page()
        self.reset()

    # ------------------------------------------------------------------ UI
    def _build_health_page(self) -> None:
        page = self.frames["health"]
        page.columnconfigure(0, weight=1)
        page.rowconfigure(2, weight=1)

        heading = ttk.Frame(page)
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(heading, text="BMI088 设备健康总览", style="Section.TLabel").pack(side="left")
        self.health_summary_var = tk.StringVar(master=page)
        ttk.Label(heading, textvariable=self.health_summary_var, style="Muted.TLabel").pack(
            side="right"
        )

        cards = ttk.Frame(page)
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for column in range(6):
            cards.columnconfigure(column, weight=1, uniform="bmi-kpi")
        definitions = (
            ("window", "推理窗口", "", COLORS["cyan"]),
            ("class", "识别结果", "", COLORS["blue"]),
            ("confidence", "置信度", "%", COLORS["purple"]),
            ("temperature", "当前温度", "°C", COLORS["amber"]),
            ("rise", "相对温升", "°C", COLORS["red"]),
            ("inference", "推理耗时", "ms", COLORS["green"]),
        )
        self.cards: dict[str, MetricCard] = {}
        for column, (key, title, unit, color) in enumerate(definitions):
            card = MetricCard(cards, title, "--", unit, color, "等待遥测数据")
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 4, 0))
            self.cards[key] = card

        body = ttk.Frame(page)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        trend_box = ttk.Frame(body, style="Card.TFrame", padding=(10, 8))
        trend_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        trend_box.columnconfigure(0, weight=1)
        trend_box.rowconfigure(0, weight=1)
        self.trend = BmiTrendChart(trend_box)
        self.trend.grid(row=0, column=0, sticky="nsew")

        side = ttk.Frame(body)
        side.grid(row=0, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)

        gauge_box = ttk.Frame(side, style="Card.TFrame", padding=(10, 8))
        gauge_box.grid(row=0, column=0, sticky="ew")
        self.gauge = ScoreGauge(gauge_box, width=280, height=150)
        self.gauge.pack(fill="x")
        self.score_actual_var = tk.StringVar(master=page)
        self.score_actual_label = tk.Label(
            gauge_box,
            textvariable=self.score_actual_var,
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.score_actual_label.pack(pady=(0, 2))
        ttk.Label(
            gauge_box,
            text="归一化仪表：设备分数 9.00 对应仪表 700",
            style="SurfaceMuted.TLabel",
            font=("Microsoft YaHei UI", 7),
        ).pack()

        model_box = ttk.Frame(side, style="Card.TFrame", padding=(12, 10))
        model_box.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(model_box, text="模型状态", style="SurfaceMuted.TLabel",
                  font=("Microsoft YaHei UI", 7, "bold")).pack(anchor="w")
        self.model_var = tk.StringVar(master=page)
        ttk.Label(
            model_box,
            textvariable=self.model_var,
            style="Surface.TLabel",
            justify="left",
            wraplength=305,
        ).pack(anchor="w", pady=(5, 0))
        self.baseline_var = tk.StringVar(master=page)
        ttk.Label(model_box, textvariable=self.baseline_var, style="SurfaceMuted.TLabel").pack(
            anchor="w", pady=(6, 0)
        )

        fusion_box = ttk.Frame(side, style="Card.TFrame", padding=(10, 8))
        fusion_box.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.fusion = FusionStatusChart(fusion_box, height=154)
        self.fusion.pack(fill="x")

        controls = ttk.Frame(page, style="Card.TFrame", padding=(12, 9))
        controls.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(controls, text="设备控制", style="SurfaceMuted.TLabel",
                  font=("Microsoft YaHei UI", 7, "bold")).pack(side="left", padx=(0, 10))
        for text, command, style in (
            ("校准基线 (b)", "b", "Accent.TButton"),
            ("连续监测 (m)", "m", "Accent.TButton"),
            ("采集特征 (p)", "p", "TButton"),
            ("读取温度 (t)", "t", "TButton"),
            ("LCD 下一页 (u)", "u", "TButton"),
            ("模型诊断 (i)", "i", "TButton"),
        ):
            ttk.Button(
                controls,
                text=text,
                style=style,
                command=lambda value=command: self._dispatch(value),
            ).pack(side="left", padx=3)
        self.action_var = tk.StringVar(master=page)
        ttk.Label(controls, textvariable=self.action_var, style="SurfaceMuted.TLabel").pack(
            side="right", padx=(10, 0)
        )

    def _build_waveform_page(self) -> None:
        page = self.frames["waveform"]
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=3)
        page.rowconfigure(2, weight=2)
        row = ttk.Frame(page)
        row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(row, text="振动波形与频带能量", style="Section.TLabel").pack(side="left")
        self.wave_status_var = tk.StringVar(master=page)
        ttk.Label(row, textvariable=self.wave_status_var, style="Muted.TLabel").pack(side="right")

        chart_box = ttk.Frame(page, style="Card.TFrame", padding=(12, 10))
        chart_box.grid(row=1, column=0, sticky="nsew")
        chart_box.columnconfigure(0, weight=1)
        chart_box.rowconfigure(0, weight=1)
        self.waveform = WaveformChart(chart_box, height=300)
        self.waveform.grid(row=0, column=0, sticky="nsew")

        spectrum_box = ttk.Frame(page, style="Card.TFrame", padding=(12, 9))
        spectrum_box.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        spectrum_box.columnconfigure(0, weight=1)
        spectrum_box.rowconfigure(1, weight=1)
        spectrum_title = ttk.Frame(spectrum_box, style="Card.TFrame")
        spectrum_title.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(
            spectrum_title,
            text="12 频带相对谱值（12.5–390 Hz）",
            style="Surface.TLabel",
            font=("Microsoft YaHei UI", 8, "bold"),
        ).pack(side="left")
        self.spectrum_status_var = tk.StringVar(master=page)
        ttk.Label(
            spectrum_title,
            textvariable=self.spectrum_status_var,
            style="SurfaceMuted.TLabel",
        ).pack(side="right")
        self.spectrum = SpectrumBars(spectrum_box, height=200)
        self.spectrum.grid(row=1, column=0, sticky="nsew")

        note = ttk.Frame(page, style="Card.TFrame", padding=(12, 9))
        note.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            note,
            text=(
                "设备端以 800 Hz 采集 512 点（约 640 ms/窗口），上位机显示下采样后的 64 点波形。"
                "推理仍使用完整窗口，图形降采样不会改变模型结果。频带图来自设备端 26 维特征中的 F12–F23。"
            ),
            style="SurfaceMuted.TLabel",
        ).pack(side="left")
        ttk.Button(note, text="采一帧特征 (p)", command=lambda: self._dispatch("p")).pack(
            side="right"
        )

    def _build_features_page(self) -> None:
        page = self.frames["features"]
        page.columnconfigure(0, weight=2)
        page.columnconfigure(1, weight=3)
        page.rowconfigure(1, weight=1)

        ttk.Label(page, text="可解释端侧推理", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.feature_status_var = tk.StringVar(master=page)
        ttk.Label(page, textvariable=self.feature_status_var, style="Muted.TLabel").grid(
            row=0, column=1, sticky="e", pady=(0, 8)
        )

        explain_box = ttk.Frame(page, style="Card.TFrame", padding=(12, 10))
        explain_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        explain_box.columnconfigure(0, weight=1)
        explain_box.rowconfigure(0, weight=1)
        self.explanation = ExplanationBars(explain_box, height=290)
        self.explanation.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            explain_box,
            text=(
                "贡献度说明模型为何判定异常；它不是传感器原始幅值。"
                "ONE_CLASS_FALLBACK 下显示的是相对正常基线的主要偏离特征。"
            ),
            style="SurfaceMuted.TLabel",
            wraplength=430,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        table_box = ttk.Frame(page, style="Card.TFrame")
        table_box.grid(row=1, column=1, sticky="nsew")
        table_box.columnconfigure(0, weight=1)
        table_box.rowconfigure(0, weight=1)
        columns = ("index", "feature", "value", "unit", "scaled")
        self.feature_tree = ttk.Treeview(table_box, columns=columns, show="headings")
        headings = {
            "index": "#",
            "feature": "特征名称",
            "value": "工程值",
            "unit": "单位",
            "scaled": "协议值（×10⁶）",
        }
        widths = {"index": 42, "feature": 180, "value": 130, "unit": 75, "scaled": 145}
        for column in columns:
            self.feature_tree.heading(column, text=headings[column])
            self.feature_tree.column(
                column,
                width=widths[column],
                stretch=column in {"feature", "value", "scaled"},
                anchor="e" if column in {"index", "value", "scaled"} else "w",
            )
        scrollbar = ttk.Scrollbar(table_box, orient="vertical", command=self.feature_tree.yview)
        self.feature_tree.configure(yscrollcommand=scrollbar.set)
        self.feature_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        for index, (name, unit) in enumerate(zip(FEATURE_NAMES, FEATURE_UNITS, strict=True)):
            self.feature_tree.insert(
                "", "end", iid=f"feature-{index:02d}",
                values=(index, FEATURE_DISPLAY_NAMES[name], "--", unit, "--"),
            )

        capture = ttk.Frame(page, style="Card.TFrame", padding=(12, 9))
        capture.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        warning = (
            "安全提示：每次采集约 0.64 s，并输出 512 行数据。请确认旋转机构、线束及防护罩可靠；"
            "禁止通过拆除防护或人为损坏设备制造故障样本。"
        )
        tk.Label(
            capture,
            text=warning,
            background=COLORS["surface"],
            foreground=COLORS["amber"],
            font=("Microsoft YaHei UI", 8, "bold"),
        ).pack(side="left", fill="x", expand=True)
        for command, label in (
            ("0", "正常 0"),
            ("1", "不平衡 1"),
            ("2", "松动 2"),
            ("3", "摩擦 3"),
            ("4", "轴承 4"),
        ):
            ttk.Button(
                capture,
                text=label,
                style="TButton" if command == "0" else "Danger.TButton",
                command=lambda value=command: self._capture_labelled_window(value),
            ).pack(side="left", padx=3)

    def _build_events_page(self) -> None:
        page = self.frames["events"]
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(page)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(toolbar, text="健康状态变化记录", style="Section.TLabel").pack(side="left")
        ttk.Label(
            toolbar,
            text="仅记录状态变化；重复的 q 遥测快照会自动去重。",
            style="Muted.TLabel",
        ).pack(side="left", padx=(12, 0))
        ttk.Button(toolbar, text="清空", command=self._clear_events).pack(side="right")
        if self.export_callback is not None:
            ttk.Button(toolbar, text="导出会话", command=self.export_callback).pack(
                side="right", padx=(0, 6)
            )

        table = ttk.Frame(page, style="Card.TFrame")
        table.grid(row=1, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        columns = ("time", "window", "transition", "class", "score", "temp", "detail")
        self.event_tree = ttk.Treeview(table, columns=columns, show="headings")
        headings = {
            "time": "上位机时间", "window": "窗口", "transition": "健康状态变化",
            "class": "识别结果", "score": "异常分数", "temp": "温度", "detail": "详细信息",
        }
        widths = {
            "time": 90, "window": 75, "transition": 165, "class": 115,
            "score": 80, "temp": 85, "detail": 330,
        }
        for column in columns:
            self.event_tree.heading(column, text=headings[column])
            self.event_tree.column(column, width=widths[column], stretch=column == "detail")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.event_tree.yview)
        self.event_tree.configure(yscrollcommand=scrollbar.set)
        self.event_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.event_tree.tag_configure("ok", foreground=COLORS["green"])
        self.event_tree.tag_configure("warn", foreground=COLORS["amber"])
        self.event_tree.tag_configure("alarm", foreground=COLORS["red"])
        self.event_tree.tag_configure("sensor", foreground=COLORS["purple"])
        self.event_tree.tag_configure("muted", foreground=COLORS["muted"])

    # ------------------------------------------------------------- public API
    def reset(self) -> None:
        """Clear all connection-specific state while keeping the pages built."""

        self._last_window_id = None
        self._last_health = None
        self._latest_snapshot = None
        self._wave_window = None
        self._explanation_window = None
        self._explanations.clear()
        self._event_keys.clear()
        self._event_key_order.clear()
        self._event_rows.clear()
        self.trend.clear()
        self.waveform.clear()
        self.spectrum.clear()
        self.explanation.clear()
        self.fusion.clear()
        self.gauge.set_score(0)
        for card in self.cards.values():
            card.set("--", "等待遥测数据")
        self.score_actual_var.set("实际分数 -- · 健康状态未知")
        self.score_actual_label.configure(foreground=COLORS["muted"])
        self.health_summary_var.set("传感器 -- · 监测 -- · 设备事件 0")
        self.model_var.set(MODEL_DESCRIPTIONS["UNKNOWN"])
        self.baseline_var.set("正常基线 -- 个窗口")
        self.action_var.set("")
        self.wave_status_var.set("等待 BMI_WAVE 波形")
        self.spectrum_status_var.set("采集特征后显示")
        self.feature_status_var.set("26 维设备端特征 · 定点整数协议")
        self._reset_feature_table()
        self._clear_events(clear_memory=False)

    def update_telemetry(self, snapshot: BmiTelemetrySnapshot) -> bool:
        """Render one snapshot and return ``True`` only for a new window ID."""

        if not isinstance(snapshot, BmiTelemetrySnapshot):
            raise TypeError("snapshot must be BmiTelemetrySnapshot")

        new_window = self._last_window_id is None or snapshot.window_id != self._last_window_id
        previous_health = self._last_health
        self._latest_snapshot = snapshot

        mode_label = MODE_LABELS.get(snapshot.mode.strip().upper(), snapshot.mode)
        class_label = self._class_label(snapshot.class_name)
        health = snapshot.health.strip().upper() or "UNKNOWN"
        health_label = HEALTH_LABELS.get(health, health)
        self.cards["window"].set(snapshot.window_id, mode_label)
        self.cards["class"].set(class_label, health_label)
        self.cards["confidence"].set(
            f"{snapshot.confidence_permille / 10.0:.1f}",
            f"千分制协议值 {snapshot.confidence_permille}",
        )
        temperature_label = TEMPERATURE_LABELS.get(
            snapshot.temperature_level.strip().upper(), snapshot.temperature_level
        )
        self.cards["temperature"].set(
            f"{snapshot.temperature_c:.1f}", temperature_label
        )
        self.cards["rise"].set(f"{snapshot.rise_c:+.1f}", "相对正常基线")
        self.cards["inference"].set(
            f"{snapshot.inference_us / 1000.0:.2f}", f"设备端 {snapshot.inference_us} μs"
        )

        normalized_score = min(
            1000,
            max(0, round(snapshot.score_x100 * self.SCORE_GAUGE_ALARM / self.SCORE_ALARM_X100)),
        )
        self.gauge.set_score(normalized_score)
        self.score_actual_var.set(
            f"实际分数 {snapshot.score_x100 / 100.0:.2f}（协议值 {snapshot.score_x100}）"
            f" · 健康状态 {health_label}"
        )
        health_color = self._health_color(health)
        self.score_actual_label.configure(foreground=health_color)
        sensor = "就绪" if snapshot.sensor_ready else "异常"
        monitor = "开启" if snapshot.monitor else "关闭"
        self.health_summary_var.set(
            f"传感器 {sensor} · 连续监测 {monitor} · 设备事件 {snapshot.event_count}"
        )
        self.fusion.set_state(
            snapshot.score_x100,
            snapshot.temperature_millideg_c,
            snapshot.rise_millideg_c,
            health,
            snapshot.sensor_ready,
        )
        model_state = snapshot.model.strip().upper() or "UNKNOWN"
        description = MODEL_DESCRIPTIONS.get(
            model_state,
            f"{model_state}：设备已上报模型标识；详细含义以固件版本说明为准。",
        )
        self.model_var.set(description)
        self.baseline_var.set(
            f"正常基线 {snapshot.baseline_windows} 个窗口 · 本地状态变化 "
            f"{len(self._event_rows)} 条"
        )

        if new_window:
            chart_time = snapshot.timestamp_ms / 1000.0 if snapshot.timestamp_ms else time.monotonic()
            self.trend.add_point(
                chart_time,
                snapshot.score_x100,
                snapshot.temperature_millideg_c,
                snapshot.confidence_permille,
            )
            self._last_window_id = snapshot.window_id
            if self._explanation_window != snapshot.window_id:
                self._explanation_window = snapshot.window_id
                self._explanations.clear()
                self.explanation.clear()

        if previous_health is None:
            self._last_health = health
            if health in {"WARN", "ALARM", "SENSOR", "ERROR"}:
                self.observe_event(
                    health,
                    window_id=snapshot.window_id,
                    previous="START",
                    class_name=snapshot.class_name,
                    score_x100=snapshot.score_x100,
                    temperature_mc=snapshot.temperature_millideg_c,
                    detail="设备首次上报的健康状态不是正常",
                )
        elif health != previous_health:
            self.observe_event(
                health,
                window_id=snapshot.window_id,
                previous=previous_health,
                class_name=snapshot.class_name,
                score_x100=snapshot.score_x100,
                temperature_mc=snapshot.temperature_millideg_c,
                detail=f"设备在“{mode_label}”模式下发生健康状态变化",
            )
            self._last_health = health
        return new_window

    def update_wave(self, snapshot: BmiWaveSnapshot) -> None:
        """Render a valid 64-point signed waveform snapshot."""

        if not isinstance(snapshot, BmiWaveSnapshot):
            raise TypeError("snapshot must be BmiWaveSnapshot")
        if not snapshot.valid:
            self.wave_status_var.set(
                f"无效波形 · 窗口 {snapshot.window_id} · {snapshot.encoding} · "
                f"{len(snapshot.points)}/{snapshot.declared_points} 点"
            )
            return
        if self._wave_window == snapshot.window_id and tuple(snapshot.points) == getattr(
            self, "_last_wave_points", ()
        ):
            return
        self._wave_window = snapshot.window_id
        self._last_wave_points = tuple(snapshot.points)
        self.waveform.set_samples(snapshot.points)
        self.wave_status_var.set(
            f"窗口 {snapshot.window_id} · {snapshot.declared_points} 点 · {snapshot.encoding}"
        )

    def update_explanation(
        self,
        explanation: BmiExplanationSnapshot | ProtocolMessage,
    ) -> None:
        """Merge one ranked v1 or legacy explanation into the Top-3 chart."""

        if isinstance(explanation, BmiExplanationSnapshot):
            window_id = explanation.window_id
            rank = explanation.rank
            feature = explanation.feature
            contribution = explanation.contribution_x100
        elif isinstance(explanation, ProtocolMessage):
            if explanation.kind not in {MessageKind.BMI_EXPLAIN, MessageKind.EXPLAIN}:
                return
            window_id = explanation.get_int("WINDOW", self._last_window_id or 0) or 0
            rank = explanation.get_int("RANK", 0) or 0
            feature = explanation.get("FEATURE", "unknown") or "unknown"
            contribution = explanation.get_int("CONTRIB_X100", 0) or 0
        else:
            raise TypeError("explanation must be BmiExplanationSnapshot or ProtocolMessage")

        if rank <= 0:
            return
        if self._explanation_window != window_id:
            self._explanation_window = window_id
            self._explanations.clear()
        feature_label = self._feature_label(feature)
        self._explanations[rank] = (feature_label, contribution)
        ordered = [self._explanations[key] for key in sorted(self._explanations)[:3]]
        self.explanation.set_items(ordered)
        self.feature_status_var.set(
            f"解释窗口 {window_id} · 已收到 {len(ordered)}/3 个主要贡献特征"
        )

    def update_features(self, message: ProtocolMessage) -> None:
        """Populate the fixed 26-feature table from a legacy ``FEATURES`` line."""

        if not isinstance(message, ProtocolMessage) or message.kind is not MessageKind.FEATURES:
            return
        count = message.get_int("COUNT", 0) or 0
        spectrum_values: list[float] = []
        for index, (name, unit) in enumerate(zip(FEATURE_NAMES, FEATURE_UNITS, strict=True)):
            raw_text = message.get(f"F{index}")
            value_text = "--"
            if raw_text is not None:
                try:
                    value_text = f"{int(raw_text, 0) / 1_000_000.0:.6g}"
                except ValueError:
                    value_text = "无效"
            if 12 <= index <= 23:
                try:
                    spectrum_values.append(int(raw_text, 0) / 1_000_000.0 if raw_text else 0.0)
                except ValueError:
                    spectrum_values.append(0.0)
            self.feature_tree.item(
                f"feature-{index:02d}",
                values=(index, FEATURE_DISPLAY_NAMES[name], value_text, unit,
                        raw_text if raw_text is not None else "--"),
            )
        window_id = message.get_int("WINDOW", 0) or 0
        self.spectrum.set_features(spectrum_values)
        self.spectrum_status_var.set(f"特征窗口 {window_id} · F12–F23")
        self.feature_status_var.set(f"特征窗口 {window_id} · 已收到 {count}/26 个值")

    def update_temperature(self, message: ProtocolMessage) -> None:
        """Refresh temperature cards without inserting a duplicate trend point."""

        if not isinstance(message, ProtocolMessage) or message.kind is not MessageKind.TEMP_NOW:
            return
        temperature_mc = message.get_int("TEMP_MC", 0) or 0
        baseline_mc = message.get_int("BASELINE_MC", 0) or 0
        rise_mc = message.get_int("RISE_MC", 0) or 0
        level = message.get("TEMP_LEVEL", "UNKNOWN") or "UNKNOWN"
        level_label = TEMPERATURE_LABELS.get(level.strip().upper(), level)
        self.cards["temperature"].set(f"{temperature_mc / 1000.0:.1f}", level_label)
        self.cards["rise"].set(f"{rise_mc / 1000.0:+.1f}", "相对正常基线")
        latest_score = self._latest_snapshot.score_x100 if self._latest_snapshot else 0
        latest_health = self._latest_snapshot.health if self._latest_snapshot else "UNKNOWN"
        latest_sensor = self._latest_snapshot.sensor_ready if self._latest_snapshot else True
        self.fusion.set_state(latest_score, temperature_mc, rise_mc, latest_health, latest_sensor)
        self.baseline_var.set(
            f"温度基线 {baseline_mc / 1000.0:.1f} °C · 本地状态变化 "
            f"{len(self._event_rows)} 条"
        )

    def observe_event(
        self,
        event: ProtocolMessage | str,
        *,
        window_id: int | None = None,
        previous: str | None = None,
        class_name: str | None = None,
        score_x100: int | None = None,
        temperature_mc: int | None = None,
        detail: str | None = None,
    ) -> bool:
        """Record an explicit event or a legacy health transition once.

        Returns ``True`` when a row was inserted and ``False`` when the record
        was irrelevant or a duplicate.
        """

        snapshot = self._latest_snapshot
        if isinstance(event, ProtocolMessage):
            if event.kind is not MessageKind.EVENT:
                target = event.kind.value
                source = self._last_health or "DEVICE"
                window = event.get_int("WINDOW", window_id if window_id is not None else 0) or 0
                category = class_name or (snapshot.class_name if snapshot else "--")
                score = score_x100 if score_x100 is not None else (snapshot.score_x100 if snapshot else 0)
                temperature = (temperature_mc if temperature_mc is not None else
                               (snapshot.temperature_millideg_c if snapshot else 0))
                description = event.raw
            else:
                target = event.get("TO", event.get("HEALTH", "EVENT")) or "EVENT"
                source = event.get("FROM", previous or self._last_health or "UNKNOWN") or "UNKNOWN"
                window = event.get_int("WINDOW", window_id if window_id is not None else 0) or 0
                category = event.get("CLASS", class_name or (snapshot.class_name if snapshot else "--"))
                score = event.get_int(
                    "SCORE_X100", score_x100 if score_x100 is not None else (snapshot.score_x100 if snapshot else 0)
                ) or 0
                temperature = event.get_int(
                    "TEMP_MC",
                    temperature_mc if temperature_mc is not None else (
                        snapshot.temperature_millideg_c if snapshot else 0
                    ),
                ) or 0
                description = event.get("DETAIL", event.raw) or event.raw
        else:
            target = str(event).strip().upper() or "UNKNOWN"
            source = (previous or self._last_health or "UNKNOWN").strip().upper()
            window = window_id if window_id is not None else (snapshot.window_id if snapshot else 0)
            category = class_name or (snapshot.class_name if snapshot else "--")
            score = score_x100 if score_x100 is not None else (snapshot.score_x100 if snapshot else 0)
            temperature = (
                temperature_mc
                if temperature_mc is not None
                else (snapshot.temperature_millideg_c if snapshot else 0)
            )
            description = detail or "健康状态变化"

        key = (window, source.upper(), target.upper(), str(category), int(score), description)
        if key in self._event_keys:
            return False
        if len(self._event_key_order) >= self.MAX_EVENTS:
            oldest = self._event_key_order.popleft()
            self._event_keys.discard(oldest)
        self._event_key_order.append(key)
        self._event_keys.add(key)

        values = (
            datetime.now().strftime("%H:%M:%S"),
            str(window),
            f"{self._health_label(source)} → {self._health_label(target)}",
            self._class_label(str(category)),
            f"{int(score) / 100.0:.2f}",
            f"{int(temperature) / 1000.0:.1f} °C",
            self._translate_detail(description),
        )
        self._event_rows.append(values)
        tag = self._health_tag(target)
        item = self.event_tree.insert("", 0, values=values, tags=(tag,))
        children = self.event_tree.get_children("")
        if len(children) > self.MAX_EVENTS:
            self.event_tree.delete(children[-1])
        self.event_tree.see(item)
        self.baseline_var.set(
            (self.baseline_var.get().split(" · 本地状态变化", 1)[0])
            + f" · 本地状态变化 {len(self._event_rows)} 条"
        )
        return True

    def hide_tabs(self) -> None:
        """Hide all BMI pages without destroying their current state."""

        for frame, _title in self.tab_specs:
            try:
                self.notebook.hide(frame)
            except tk.TclError:
                pass

    def show_tabs(self) -> None:
        """Restore all BMI pages in their declared order."""

        for frame, title in self.tab_specs:
            self.notebook.add(frame, text=title)

    # --------------------------------------------------------------- helpers
    def _dispatch(self, command: str) -> None:
        try:
            self.send_command(command)
            self.action_var.set(f"已发送 {command} · {datetime.now().strftime('%H:%M:%S')}")
        except Exception as error:  # Keep a button callback from breaking Tk's event loop.
            self.action_var.set(f"命令 {command} 发送失败：{type(error).__name__}")

    def _capture_labelled_window(self, command: str) -> None:
        if command != "0":
            labels = {"1": "不平衡", "2": "松动", "3": "摩擦", "4": "轴承"}
            proceed = messagebox.askyesno(
                "故障样本采集确认",
                f"即将采集“{labels.get(command, command)}”标签窗口（约 0.64 s）。\n\n"
                "请确认：\n"
                "1. 设备已断开危险执行机构，或故障状态来自安全测试台；\n"
                "2. 防护罩已闭合，线束和人员均处于安全位置；\n"
                "3. 不会通过人为损坏设备制造样本。\n\n"
                "确认继续采集吗？",
                parent=self.notebook.winfo_toplevel(),
            )
            if not proceed:
                self.action_var.set("已取消标签样本采集")
                return
        self._dispatch(command)

    def _reset_feature_table(self) -> None:
        for index, (name, unit) in enumerate(zip(FEATURE_NAMES, FEATURE_UNITS, strict=True)):
            self.feature_tree.item(
                f"feature-{index:02d}",
                values=(index, FEATURE_DISPLAY_NAMES[name], "--", unit, "--"),
            )

    def _clear_events(self, *, clear_memory: bool = True) -> None:
        children = self.event_tree.get_children("")
        if children:
            self.event_tree.delete(*children)
        if clear_memory:
            self._event_keys.clear()
            self._event_key_order.clear()
            self._event_rows.clear()

    @staticmethod
    def _health_color(health: str) -> str:
        health = health.upper()
        if health in {"ALARM", "ERROR"}:
            return COLORS["red"]
        if health == "WARN":
            return COLORS["amber"]
        if health == "SENSOR":
            return COLORS["purple"]
        if health == "OK":
            return COLORS["green"]
        return COLORS["muted"]

    @staticmethod
    def _health_tag(health: str) -> str:
        health = health.upper()
        if health in {"ALARM", "ERROR"}:
            return "alarm"
        if health == "WARN":
            return "warn"
        if health == "SENSOR":
            return "sensor"
        if health == "OK":
            return "ok"
        return "muted"

    @staticmethod
    def _class_label(class_name: str) -> str:
        normalized = class_name.strip().lower()
        return CLASS_LABELS.get(normalized, class_name or "未知")

    @staticmethod
    def _health_label(health: str) -> str:
        normalized = health.strip().upper()
        return HEALTH_LABELS.get(normalized, health or "未知")

    @staticmethod
    def _feature_label(feature: str) -> str:
        normalized = feature.strip().lower()
        if normalized in FEATURE_DISPLAY_NAMES:
            return FEATURE_DISPLAY_NAMES[normalized]
        alias = normalized.removeprefix("feature_").removeprefix("feature-")
        if alias.isdigit():
            index = int(alias)
            if 0 <= index < len(FEATURE_LABELS):
                return FEATURE_LABELS[index]
        return feature or "未知特征"

    @staticmethod
    def _translate_detail(detail: str) -> str:
        translations = {
            "Health transition": "健康状态变化",
            "First reported health is not OK": "设备首次上报的健康状态不是正常",
        }
        return translations.get(detail, detail)
