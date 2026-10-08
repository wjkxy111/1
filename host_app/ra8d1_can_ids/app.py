"""Unified desktop studio for RA8D1 CAN and BMI088 edge-AI firmware."""

from __future__ import annotations

from collections import deque
from datetime import datetime
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from .bmi_demo import BmiDemoSource
from .demo import DemoSource
from .models import (
    BmiExplanationSnapshot,
    BmiTelemetrySnapshot,
    BmiWaveSnapshot,
    CanFrameSnapshot,
    DeviceKind,
    MessageKind,
    ProtocolMessage,
    TelemetrySnapshot,
    device_kind_from_message,
    reason_labels,
)
from .protocol import ProtocolParser
from .serial_link import SerialLink, list_serial_port_info, preferred_serial_port
from .session import SessionRecorder, SessionReplay, load_jsonl
from .widgets import (
    COLORS,
    MetricCard,
    CanBusTopology,
    ReasonDonutChart,
    ScoreGauge,
    TimelineChart,
    apply_theme,
    configure_tree_tags,
    human_count,
    score_tag,
)


POLL_INTERVAL_MS = 500
UI_TICK_MS = 50
MAX_CONSOLE_LINES = 2_000
MAX_TABLE_ROWS = 500

MODE_CN = {
    "WAITING": "等待数据",
    "LEARNING": "学习中",
    "MONITORING": "监测中",
    "MONITOR": "监测中",
    "CALIBRATE": "校准中",
    "IDLE": "空闲",
    "UNKNOWN": "未知状态",
}


def _mode_cn(mode: str) -> str:
    normalized = mode.strip().upper()
    return MODE_CN.get(normalized, mode or "未知状态")


class EdgeIdsStudio:
    """Unified host dashboard. All Tk mutations stay on the UI thread."""

    def __init__(self, root: tk.Tk, *, port: str | None = None, baud: int = 115200,
                 demo: bool | str = False, replay: str | None = None) -> None:
        self.root = root
        self.root.title("RA8D1 端侧 AI 综合工作台")
        apply_theme(root)
        self._configure_window_geometry()
        if self.root.tk.call("tk", "windowingsystem") == "win32":
            # A dashboard benefits from the entire Windows work area, and this
            # prevents the restored high-DPI client size from reaching under
            # the taskbar on 125%/150% displays.
            self.root.state("zoomed")

        self.parser = ProtocolParser()
        self.link: SerialLink | None = None
        self.demo_source: DemoSource | BmiDemoSource | None = None
        self.device_kind = DeviceKind.UNKNOWN
        self._can_probe_sent = False
        self.recorder = SessionRecorder()
        self._replay_queue: queue.Queue[ProtocolMessage] = queue.Queue()
        self._replay_stop = threading.Event()
        self._replay_thread: threading.Thread | None = None
        self._closing = False
        self._last_poll = 0.0
        self._last_port_scan = 0.0
        self._port_descriptions: dict[str, str] = {}
        self._console_lines = 0
        self._event_keys: deque[str] = deque(maxlen=1000)
        self._event_key_set: set[str] = set()
        self._profile_rows: dict[str, str] = {}
        self._frame_rows: dict[tuple[int, str], str] = {}
        self._frame_counts: dict[tuple[int, str], int] = {}
        self._last_frame_marker: dict[tuple[int, str], tuple[object, ...]] = {}
        self._last_frame_time: dict[tuple[int, str], int] = {}
        self._latest_snapshot = TelemetrySnapshot()
        self._capture_enabled = False
        self._bmi_explanations: dict[int, BmiExplanationSnapshot] = {}
        self._reason_counts: dict[str, int] = {label: 0 for label in reason_labels(0x7F)}

        self.port_var = tk.StringVar(value=port or "")
        self.baud_var = tk.StringVar(value=str(baud))
        self.source_var = tk.StringVar(value="未连接")
        self.status_var = tk.StringVar(value="未连接")
        self.mode_var = tk.StringVar(value="等待数据")
        self.protocol_var = tk.StringVar(value="协议：等待设备")
        self.record_var = tk.StringVar(value="开始录制")
        self.command_var = tk.StringVar()
        self.brand_var = tk.StringVar(value="RA8D1 端侧 AI 综合工作台")
        self.subtitle_var = tk.StringVar(
            value="一个上位机 · 两套端侧 AI 工程 · 自动识别固件")
        self.demo_var = tk.StringVar(value="CAN 异常检测")

        self._build_ui()
        self._refresh_ports()
        if port:
            self.port_var.set(port)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(UI_TICK_MS, self._tick)
        if replay:
            self.root.after(150, lambda: self.open_replay(replay))
        elif demo:
            demo_name = str(demo).lower() if isinstance(demo, str) else "can"
            self.root.after(150, lambda: self.start_demo(demo_name))

    def _configure_window_geometry(self) -> None:
        """Keep the same visual workspace after enabling native high DPI."""

        try:
            # Tk scaling is pixels per typographic point: 96 DPI == 4/3.
            dpi_ratio = max(1.0, float(self.root.tk.call("tk", "scaling")) / (96.0 / 72.0))
        except (tk.TclError, TypeError, ValueError):
            dpi_ratio = 1.0
        screen_width = max(1024, self.root.winfo_screenwidth())
        screen_height = max(720, self.root.winfo_screenheight())
        width = min(round(1440 * dpi_ratio), round(screen_width * 0.94))
        height = min(round(900 * dpi_ratio), round(screen_height * 0.91))
        minimum_width = min(width, round(1120 * dpi_ratio))
        minimum_height = min(height, round(720 * dpi_ratio))
        left = max(0, (screen_width - width) // 2)
        top = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{left}+{top}")
        self.root.minsize(minimum_width, minimum_height)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, padding=(18, 13, 18, 14))
        shell.pack(fill="both", expand=True)
        self._build_header(shell)
        self.notebook = ttk.Notebook(shell)
        self.notebook.pack(fill="both", expand=True, pady=(12, 0))

        self.overview_tab = ttk.Frame(self.notebook, padding=(2, 13))
        self.frames_tab = ttk.Frame(self.notebook, padding=(2, 13))
        self.events_tab = ttk.Frame(self.notebook, padding=(2, 13))
        self.profiles_tab = ttk.Frame(self.notebook, padding=(2, 13))
        self.visual_tab = ttk.Frame(self.notebook, padding=(2, 13))
        self.console_tab = ttk.Frame(self.notebook, padding=(2, 13))
        self.notebook.add(self.overview_tab, text="  总览  ")
        self.notebook.add(self.visual_tab, text="  系统图谱  ")
        self.notebook.add(self.frames_tab, text="  实时帧  ")
        self.notebook.add(self.events_tab, text="  异常事件  ")
        self.notebook.add(self.profiles_tab, text="  ID 画像  ")
        self._build_overview()
        self._build_visuals()
        self._build_frames()
        self._build_events()
        self._build_profiles()
        # Imported here to keep the protocol/data layer usable headlessly.
        from .bmi_view import BmiDashboard
        self.bmi_dashboard = BmiDashboard(self.notebook, self.send_command)
        self.notebook.add(self.console_tab, text="  原始协议  ")
        self._build_console()
        self._show_device(DeviceKind.CAN_IDS, reset=False)

    def _build_header(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x")
        brand = ttk.Frame(top)
        brand.pack(side="left", fill="x", expand=True)
        ttk.Label(brand, textvariable=self.brand_var, style="Title.TLabel").pack(anchor="w")
        ttk.Label(brand, textvariable=self.subtitle_var,
                  style="Muted.TLabel").pack(anchor="w", pady=(1, 0))

        status = tk.Label(top, textvariable=self.status_var, bg="#35212A", fg=COLORS["red"],
                          font=("Microsoft YaHei UI", 8, "bold"), padx=12, pady=6)
        status.pack(side="right", padx=(8, 0))
        self.status_badge = status
        mode = tk.Label(top, textvariable=self.mode_var, bg="#173246", fg=COLORS["cyan"],
                        font=("Microsoft YaHei UI", 8, "bold"), padx=12, pady=6)
        mode.pack(side="right")
        self.mode_badge = mode

        bar = ttk.Frame(parent, style="Header.TFrame", padding=(12, 9))
        bar.pack(fill="x", pady=(13, 0))
        ttk.Label(bar, text="开发板串口", style="SurfaceMuted.TLabel",
                  font=("Microsoft YaHei UI", 7, "bold")).pack(side="left", padx=(0, 7))
        self.port_combo = ttk.Combobox(bar, textvariable=self.port_var, width=18)
        self.port_combo.pack(side="left")
        ttk.Button(bar, text="↻", width=3, command=self._refresh_ports).pack(side="left", padx=(5, 11))
        ttk.Label(bar, text="波特率", style="SurfaceMuted.TLabel",
                  font=("Microsoft YaHei UI", 7, "bold")).pack(side="left", padx=(0, 7))
        ttk.Combobox(bar, textvariable=self.baud_var, values=("115200", "230400", "460800"),
                     width=9, state="readonly").pack(side="left")
        self.connect_button = ttk.Button(bar, text="连接", style="Accent.TButton",
                                         command=self.toggle_connection)
        self.connect_button.pack(side="left", padx=(10, 5))
        demo_combo = ttk.Combobox(bar, textvariable=self.demo_var,
                                  values=("CAN 异常检测", "BMI088 机器健康"), width=15, state="readonly")
        demo_combo.pack(side="left", padx=(5, 2))
        ttk.Button(bar, text="启动演示", command=self._start_selected_demo).pack(side="left", padx=(2, 5))
        ttk.Button(bar, text="会话回放…", command=self.open_replay).pack(side="left", padx=5)
        ttk.Button(bar, textvariable=self.record_var,
                   command=self.toggle_recording).pack(side="left", padx=5)
        ttk.Label(bar, textvariable=self.source_var, style="SurfaceMuted.TLabel").pack(side="right")

    def _build_overview(self) -> None:
        cards = ttk.Frame(self.overview_tab)
        cards.pack(fill="x")
        specs = (
            ("fps", "总线帧率", "帧/秒", COLORS["cyan"]),
            ("load", "总线负载", "%", COLORS["blue"]),
            ("ids", "已学习 ID", "个", COLORS["purple"]),
            ("total", "累计帧数", "帧", COLORS["green"]),
            ("anomaly", "异常事件", "次", COLORS["red"]),
            ("drops", "接收丢帧", "帧", COLORS["amber"]),
        )
        self.cards: dict[str, MetricCard] = {}
        for index, (key, title, unit, color) in enumerate(specs):
            cards.columnconfigure(index, weight=1, uniform="metric")
            card = MetricCard(cards, title, "--", unit, color, "等待设备遥测")
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 5, 0))
            self.cards[key] = card

        main = ttk.Frame(self.overview_tab)
        main.pack(fill="both", expand=True, pady=(12, 0))
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)
        chart_box = ttk.Frame(main, style="Card.TFrame", padding=(12, 9))
        chart_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.timeline = TimelineChart(chart_box)
        self.timeline.pack(fill="both", expand=True)

        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        gauge_box = ttk.Frame(right, style="Card.TFrame", padding=(10, 8))
        gauge_box.pack(fill="x")
        self.gauge = ScoreGauge(gauge_box)
        self.gauge.pack(fill="x")
        self.reason_var = tk.StringVar(value="当前未检测到异常")
        tk.Label(gauge_box, textvariable=self.reason_var, bg=COLORS["surface"], fg=COLORS["green"],
                 font=("Microsoft YaHei UI", 9, "bold"), pady=5).pack()
        self.reason_label = gauge_box.winfo_children()[-1]

        controls = ttk.Frame(right, style="Card.TFrame", padding=(14, 12))
        controls.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(controls, text="端侧控制", style="SurfaceMuted.TLabel",
                  font=("Microsoft YaHei UI", 7, "bold")).pack(anchor="w", pady=(0, 8))
        grid = ttk.Frame(controls, style="Card.TFrame")
        grid.pack(fill="x")
        actions = (
            ("开始学习 (l)", "l", "Accent.TButton"),
            ("冻结模型 (m)", "m", "TButton"),
            ("攻击演示 (s)", "s", "Danger.TButton"),
            ("内部回环 (o)", "o", "TButton"),
            ("经典 CAN 发送 (c)", "c", "TButton"),
            ("CAN-FD+BRS (f)", "f", "TButton"),
            ("LCD 下一页 (u)", "u", "TButton"),
            ("刷新模型 (e)", "e", "TButton"),
        )
        for index, (label, command, style) in enumerate(actions):
            grid.columnconfigure(index % 2, weight=1)
            ttk.Button(grid, text=label, style=style,
                       command=lambda value=command: self.send_command(value)).grid(
                           row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 5, 0),
                           pady=(0, 6))
        footer = ttk.Frame(controls, style="Card.TFrame")
        footer.pack(fill="x", pady=(5, 0))
        self.health_var = tk.StringVar(value="TEC 0  ·  REC 0  ·  Bus-Off 0")
        ttk.Label(footer, textvariable=self.health_var, style="SurfaceMuted.TLabel").pack(side="left")
        ttk.Label(footer, textvariable=self.protocol_var, style="SurfaceMuted.TLabel").pack(side="right")

    def _build_visuals(self) -> None:
        """Build the graphical CAN system/topology page."""

        self.visual_tab.columnconfigure(0, weight=3)
        self.visual_tab.columnconfigure(1, weight=2)
        self.visual_tab.rowconfigure(1, weight=1)
        title = ttk.Frame(self.visual_tab)
        title.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 9))
        ttk.Label(title, text="CAN 端侧异常检测系统图谱", style="Section.TLabel").pack(side="left")
        ttk.Label(title, text="从上位机到物理总线的链路状态与异常类型分布",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))
        topology_box = ttk.Frame(self.visual_tab, style="Card.TFrame", padding=(10, 8))
        topology_box.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        topology_box.rowconfigure(0, weight=1)
        topology_box.columnconfigure(0, weight=1)
        self.can_topology = CanBusTopology(topology_box)
        self.can_topology.grid(row=0, column=0, sticky="nsew")
        reason_box = ttk.Frame(self.visual_tab, style="Card.TFrame", padding=(10, 8))
        reason_box.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        reason_box.rowconfigure(0, weight=1)
        reason_box.columnconfigure(0, weight=1)
        self.reason_donut = ReasonDonutChart(reason_box)
        self.reason_donut.grid(row=0, column=0, sticky="nsew")

    def _tree(self, parent: ttk.Frame, columns: tuple[str, ...], headings: tuple[str, ...],
              widths: tuple[int, ...]) -> ttk.Treeview:
        wrapper = ttk.Frame(parent, style="Card.TFrame")
        wrapper.pack(fill="both", expand=True)
        tree = ttk.Treeview(wrapper, columns=columns, show="headings")
        scroll_y = ttk.Scrollbar(wrapper, orient="vertical", command=tree.yview)
        scroll_x = ttk.Scrollbar(wrapper, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)
        for column, heading, width in zip(columns, headings, widths, strict=True):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=50, anchor="w", stretch=(column == columns[-1]))
        configure_tree_tags(tree)
        return tree

    def _tab_title(self, parent: ttk.Frame, title: str, subtitle: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 9))
        ttk.Label(row, text=title, style="Section.TLabel").pack(side="left")
        ttk.Label(row, text=subtitle, style="Muted.TLabel").pack(side="left", padx=(12, 0))

    def _build_frames(self) -> None:
        self._tab_title(self.frames_tab, "最新 CAN 帧", "开发板以 2 Hz 返回最新帧快照；高速全量抓包可后续接入 USB-CAN-FD")
        columns = ("age", "id", "format", "type", "dlc", "data", "count", "period", "score", "reason")
        headings = ("时间", "CAN ID", "格式", "帧类型", "长度", "数据", "观测次数", "周期", "分数", "推理结论")
        widths = (95, 100, 68, 105, 66, 330, 70, 90, 70, 160)
        self.frames_tree = self._tree(self.frames_tab, columns, headings, widths)

    def _build_events(self) -> None:
        row = ttk.Frame(self.events_tab)
        row.pack(fill="x", pady=(0, 9))
        ttk.Label(row, text="可解释异常时间线", style="Section.TLabel").pack(side="left")
        ttk.Label(row, text="异常分数与原因位均由 RA8D1 端侧计算", style="Muted.TLabel").pack(side="left", padx=(12, 0))
        ttk.Button(row, text="导出 CSV…", command=self.export_events).pack(side="right")
        columns = ("time", "source", "id", "dlc", "score", "reason", "mask")
        headings = ("时间", "来源", "CAN ID", "DLC", "分数", "异常原因", "原因位")
        widths = (155, 90, 110, 70, 80, 390, 90)
        self.events_tree = self._tree(self.events_tab, columns, headings, widths)

    def _build_profiles(self) -> None:
        row = ttk.Frame(self.profiles_tab)
        row.pack(fill="x", pady=(0, 9))
        ttk.Label(row, text="已学习的正常流量画像", style="Section.TLabel").pack(side="left")
        ttk.Label(row, text="每个 CAN ID 对应一个在线统计画像", style="Muted.TLabel").pack(side="left", padx=(12, 0))
        ttk.Button(row, text="请求画像", command=lambda: self.send_command("e")).pack(side="right")
        columns = ("index", "id", "format", "dlc", "samples", "period", "rate", "risk")
        headings = ("序号", "CAN ID", "格式", "DLC", "样本数", "平均周期", "帧率", "风险")
        widths = (55, 120, 80, 70, 100, 145, 110, 90)
        self.profiles_tree = self._tree(self.profiles_tab, columns, headings, widths)

    def _build_console(self) -> None:
        toolbar = ttk.Frame(self.console_tab)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="设备原始协议", style="Section.TLabel").pack(side="left")
        ttk.Button(toolbar, textvariable=self.record_var, command=self.toggle_recording).pack(side="right")
        ttk.Button(toolbar, text="导出会话…", command=self.export_session).pack(side="right", padx=5)
        ttk.Button(toolbar, text="清空", command=self._clear_console).pack(side="right", padx=5)
        console_box = ttk.Frame(self.console_tab, style="Card.TFrame")
        console_box.pack(fill="both", expand=True)
        self.console = tk.Text(console_box, background="#081421", foreground="#AFC8DC",
                               insertbackground=COLORS["text"], selectbackground="#214C70",
                               relief="flat", borderwidth=0, font=("Microsoft YaHei UI", 9),
                               wrap="none", padx=10, pady=9, state="disabled")
        scroll_y = ttk.Scrollbar(console_box, orient="vertical", command=self.console.yview)
        scroll_x = ttk.Scrollbar(console_box, orient="horizontal", command=self.console.xview)
        self.console.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.console.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        console_box.rowconfigure(0, weight=1)
        console_box.columnconfigure(0, weight=1)
        bottom = ttk.Frame(self.console_tab)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Label(bottom, text="单字符命令：").pack(side="left")
        entry = ttk.Entry(bottom, textvariable=self.command_var)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 5))
        entry.bind("<Return>", lambda _event: self._send_custom_command())
        ttk.Button(bottom, text="发送", command=self._send_custom_command).pack(side="left")
        ttk.Label(bottom, text="CAN: l m s o c f u i e q h  ·  BMI: 0..4 b m p t u i q h",
                  style="Muted.TLabel").pack(side="right", padx=(12, 0))

    # ------------------------------------------------------------ source I/O
    def _refresh_ports(self) -> None:
        discovered = list_serial_port_info()
        ports = [item.device for item in discovered]
        self._port_descriptions = {item.device: item.description for item in discovered}
        self.port_combo.configure(values=ports)
        current = self.port_var.get().strip()
        selected = preferred_serial_port(discovered, current)
        if selected and (not current or current not in ports):
            self.port_var.set(selected)
        if self.link is None and self.demo_source is None and self._replay_thread is None:
            if selected:
                description = self._port_descriptions.get(selected, "").strip()
                suffix = f" · {description}" if description and description != selected else ""
                self.source_var.set(f"已发现串口 · {selected}{suffix}")
            elif not current:
                self.source_var.set("未发现串口 · 可使用内置演示")

    def _start_selected_demo(self) -> None:
        self.start_demo("bmi" if "BMI" in self.demo_var.get().upper() else "can")

    def toggle_connection(self) -> None:
        if self.link is not None:
            self.disconnect()
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showinfo("请选择串口", "请选择 RA8D1 SCI3 对应的串口；也可以先启动内置演示。")
            return
        self.stop_demo()
        self.stop_replay()
        try:
            link = SerialLink(port, int(self.baud_var.get()))
            link.start()
        except Exception as error:
            messagebox.showerror("串口连接失败", str(error))
            return
        self.link = link
        self.parser.reset_identity()
        self.device_kind = DeviceKind.UNKNOWN
        self._can_probe_sent = False
        self.connect_button.configure(text="断开")
        self.source_var.set(f"开发板 · {port} · {self.baud_var.get()} 8-N-1")
        self._set_connection_status("已连接", True)
        self._log_local(f"已连接 {port}，波特率 {self.baud_var.get()}")
        # q is read-only on both v1 firmwares and also reveals device-specific
        # telemetry when the initial PROTO declaration was missed.
        self.root.after(250, lambda: self.send_command("q", quiet=True))

    def disconnect(self) -> None:
        link, self.link = self.link, None
        if link is not None:
            link.stop()
        self.connect_button.configure(text="连接")
        self.source_var.set("未连接")
        self._set_connection_status("未连接", False)

    def start_demo(self, project: str = "can") -> None:
        self.disconnect()
        self.stop_replay()
        self.parser.reset_identity()
        bmi = project.lower().startswith("bmi")
        self.demo_source = BmiDemoSource() if bmi else DemoSource()
        self._reset_views()
        self.source_var.set("BMI088 确定性机器健康演示" if bmi else "CAN 确定性攻击演示")
        self._set_connection_status("演示运行中", True, demo=True)
        for line in self.demo_source.boot_lines():
            self._ingest(self.parser.feed_line(line))
        self._log_local(f"已启动 {'BMI088 AI' if bmi else 'CAN IDS'} 演示，无需硬件")

    def stop_demo(self) -> None:
        self.demo_source = None

    def open_replay(self, path: str | None = None) -> None:
        selected = path or filedialog.askopenfilename(
            title="打开 RA8D1 会话", filetypes=(("RA8D1 会话", "*.jsonl *.log"), ("所有文件", "*.*")))
        if not selected:
            return
        try:
            records = self._load_replay_records(selected)
        except Exception as error:
            messagebox.showerror("回放失败", str(error))
            return
        if not records:
            messagebox.showwarning("会话回放", "文件中没有可解析的 RA8D1 协议记录。")
            return
        self.disconnect()
        self.stop_demo()
        self.stop_replay()
        self._reset_views()
        replay_stop = threading.Event()
        self._replay_stop = replay_stop
        replay = SessionReplay(records)

        def worker() -> None:
            # Capture this replay's event: a later replay receives a fresh
            # event, so an old sleeping worker can never resume into it.
            replay.play(self._replay_queue.put, speed=4.0, stop_event=replay_stop)

        self._replay_thread = threading.Thread(target=worker, name="ra8d1-session-replay", daemon=True)
        self._replay_thread.start()
        self.source_var.set(f"回放 · {Path(selected).name} · 4 倍速")
        self._set_connection_status("正在回放", True, demo=True)

    def _load_replay_records(self, selected: str) -> list[ProtocolMessage]:
        if Path(selected).suffix.lower() == ".jsonl":
            return load_jsonl(selected)
        records: list[ProtocolMessage] = []
        base = time.time()
        with Path(selected).open("r", encoding="utf-8-sig", errors="replace") as source:
            for index, line in enumerate(source):
                if line.strip():
                    records.append(self.parser.feed_line(line, timestamp=base + (index * 0.1)))
        return records

    def stop_replay(self) -> None:
        self._replay_stop.set()
        self._replay_thread = None
        while True:
            try:
                self._replay_queue.get_nowait()
            except queue.Empty:
                break

    def send_command(self, command: str, *, quiet: bool = False) -> None:
        command = command.strip().lower()[:1]
        if not command:
            return
        if not quiet:
            self._log_local(f"> {command}")
        if self.demo_source is not None:
            for line in self.demo_source.command(command):
                self._ingest(self.parser.feed_line(line))
            return
        if self.link is not None:
            try:
                self.link.send_command(command)
            except Exception as error:
                self._log_local(f"发送失败：{error}")
            return
        if not quiet:
            messagebox.showinfo("没有数据源", "请先连接串口或启动内置演示。")

    def _send_custom_command(self) -> None:
        value = self.command_var.get().strip()
        self.command_var.set("")
        if len(value) != 1:
            messagebox.showwarning("命令格式错误", "固件命令必须是单个 ASCII 字符。")
            return
        self.send_command(value)

    # ----------------------------------------------------------- event loop
    def _tick(self) -> None:
        if self._closing:
            return
        if self.link is not None:
            link_failed = False
            for event in self.link.drain_events(limit=250):
                if event.type == "message" and event.message is not None:
                    self._ingest(event.message)
                elif event.type == "error":
                    self._log_local(f"串口错误：{event.detail}")
                    link_failed = True
            if link_failed:
                self.disconnect()
                self._set_connection_status("链路错误", False)
        for _index in range(250):
            try:
                self._ingest(self._replay_queue.get_nowait())
            except queue.Empty:
                break
        now = time.monotonic()
        if (self.link is None and self.demo_source is None and self._replay_thread is None
                and now - self._last_port_scan >= 2.0):
            self._last_port_scan = now
            self._refresh_ports()
        if self.demo_source is not None and now - self._last_poll >= POLL_INTERVAL_MS / 1000:
            self._last_poll = now
            for line in self.demo_source.step():
                self._ingest(self.parser.feed_line(line))
        elif self.link is not None and now - self._last_poll >= POLL_INTERVAL_MS / 1000:
            self._last_poll = now
            self.send_command("q", quiet=True)
        self.root.after(UI_TICK_MS, self._tick)

    def _ingest(self, message: ProtocolMessage) -> None:
        if self._capture_enabled:
            try:
                self.recorder.ingest(message)
            except OSError as error:
                self._capture_enabled = False
                try:
                    self.recorder.stop()
                except OSError:
                    pass
                self.record_var.set("开始录制")
                self._log_local(f"录制错误：{error}")
        self._append_console(message.raw, message.kind)
        kind = message.kind
        identified = device_kind_from_message(message)
        if identified is DeviceKind.UNKNOWN:
            identified = self.parser.device_kind
        if identified is not DeviceKind.UNKNOWN and identified is not self.device_kind:
            self._show_device(identified)
        if kind is MessageKind.PROTO:
            self.protocol_var.set(f"协议：{message.get('NAME', 'RA8D1')} v{message.get('VERSION', '?')}")
        elif kind is MessageKind.BOOT:
            self.protocol_var.set("协议：兼容旧版")
        elif kind is MessageKind.TELEM:
            self._update_telem(TelemetrySnapshot.from_message(message))
        elif kind is MessageKind.FRAME:
            self._update_frame(CanFrameSnapshot.from_message(message))
        elif kind in {MessageKind.EVENT, MessageKind.LOG}:
            if self.device_kind is DeviceKind.BMI088_EDGE_AI:
                self.bmi_dashboard.observe_event(message)
            else:
                self._update_event(message)
        elif kind is MessageKind.PROFILE:
            self._update_profile(message)
        elif kind is MessageKind.BMI_TELEM:
            snapshot = BmiTelemetrySnapshot.from_message(message)
            self.bmi_dashboard.update_telemetry(snapshot)
            self.mode_var.set(_mode_cn(snapshot.mode))
            self.mode_badge.configure(fg={"CALIBRATE": COLORS["amber"],
                                          "MONITOR": COLORS["cyan"]}.get(
                                              snapshot.mode.upper(), COLORS["muted"]))
        elif kind is MessageKind.RESULT:
            snapshot = BmiTelemetrySnapshot.from_result(message)
            self.bmi_dashboard.update_telemetry(snapshot)
            self.mode_var.set(_mode_cn(snapshot.mode))
        elif kind is MessageKind.BMI_WAVE:
            self.bmi_dashboard.update_wave(BmiWaveSnapshot.from_message(message))
        elif kind is MessageKind.BMI_EXPLAIN:
            self.bmi_dashboard.update_explanation(BmiExplanationSnapshot.from_message(message))
        elif kind is MessageKind.EXPLAIN:
            self.bmi_dashboard.update_explanation(BmiExplanationSnapshot(
                window_id=0,
                rank=message.get_int("RANK", 0) or 0,
                feature=message.get("FEATURE", "unknown") or "unknown",
                contribution_x100=message.get_int("CONTRIB_X100", 0) or 0,
            ))
        elif kind is MessageKind.FEATURES:
            self.bmi_dashboard.update_features(message)
        elif kind is MessageKind.TEMP_NOW:
            self.bmi_dashboard.update_temperature(message)
        elif kind in {MessageKind.CALIBRATION, MessageKind.BEGIN,
                      MessageKind.END, MessageKind.ERROR, MessageKind.MONITOR}:
            if self.device_kind is DeviceKind.BMI088_EDGE_AI:
                self.bmi_dashboard.observe_event(message)
        elif kind in {MessageKind.DIAG, MessageKind.AI, MessageKind.CAN, MessageKind.MODEL,
                      MessageKind.SELF_TEST, MessageKind.LOOPBACK}:
            if self.device_kind is DeviceKind.CAN_IDS:
                self._merge_legacy_status(message)

    def _show_device(self, device: DeviceKind, *, reset: bool = True) -> None:
        """Switch the notebook to the connected firmware without rebuilding UI."""

        if device is DeviceKind.UNKNOWN:
            return
        changed = device is not self.device_kind
        self.device_kind = device
        can_tabs = (self.overview_tab, self.visual_tab, self.frames_tab, self.events_tab, self.profiles_tab)
        bmi_tabs = tuple(frame for frame, _title in self.bmi_dashboard.tab_specs)
        for frame in (*can_tabs, *bmi_tabs, self.console_tab):
            try:
                self.notebook.hide(frame)
            except tk.TclError:
                pass
        if device is DeviceKind.BMI088_EDGE_AI:
            desired = self.bmi_dashboard.tab_specs
            self.brand_var.set("RA8D1 BMI088 机器健康端侧 AI")
            self.subtitle_var.set("800 Hz 振动采样 · 26 维特征 · 温度融合 · 端侧推理")
        else:
            desired = (
                (self.overview_tab, "  总览  "),
                (self.visual_tab, "  系统图谱  "),
                (self.frames_tab, "  实时帧  "),
                (self.events_tab, "  异常事件  "),
                (self.profiles_tab, "  ID 画像  "),
            )
            self.brand_var.set("RA8D1 CAN-FD 端侧异常检测")
            self.subtitle_var.set("在线流量学习 · 可解释异常检测 · CAN-FD")
        for frame, title in desired:
            self.notebook.add(frame, text=title)
        self.notebook.add(self.console_tab, text="  原始协议  ")
        # `hide()` preserves a tab's hidden state in ttk. Re-adding every tab
        # can therefore leave the notebook with headers but no selected page.
        # Explicitly select the first page after each device switch.
        if desired:
            self.notebook.select(desired[0][0])
        if changed and reset:
            self._reset_views()
            self._log_local(f"已识别设备：{device.value}")
        self.mode_var.set("等待数据")
        if device is DeviceKind.CAN_IDS and self.link is not None and not self._can_probe_sent:
            self._can_probe_sent = True
            self.root.after(100, lambda: self.send_command("i", quiet=True))
            self.root.after(250, lambda: self.send_command("e", quiet=True))

    def _update_telem(self, snapshot: TelemetrySnapshot) -> None:
        self._latest_snapshot = snapshot
        mode = snapshot.mode.upper()
        self.mode_var.set(_mode_cn(mode))
        mode_color = COLORS["amber"] if "LEARN" in mode else COLORS["cyan"]
        self.mode_badge.configure(fg=mode_color)
        self.cards["fps"].set(snapshot.fps, f"总线负载 {snapshot.load_permille / 10:.1f}%")
        self.cards["load"].set(f"{snapshot.load_permille / 10:.1f}", "估算线缆占用率")
        self.cards["ids"].set(snapshot.learned_ids, "在线统计画像")
        self.cards["total"].set(human_count(snapshot.total), f"未知 ID {snapshot.unknown}")
        self.cards["anomaly"].set(snapshot.anomaly, "板端判定结果")
        self.cards["drops"].set(snapshot.dropped, "RX 软件队列")
        self.gauge.set_score(snapshot.score)
        labels = reason_labels(snapshot.reason)
        reason_text = " · ".join(labels) if labels else "当前未检测到异常"
        self.reason_var.set(reason_text)
        if snapshot.score >= 700:
            self.reason_label.configure(fg=COLORS["red"])
        elif snapshot.score >= 350:
            self.reason_label.configure(fg=COLORS["amber"])
        else:
            self.reason_label.configure(fg=COLORS["green"])
        timestamp = snapshot.timestamp_ms / 1000 if snapshot.timestamp_ms else time.monotonic()
        self.timeline.add_point(timestamp, snapshot.score, snapshot.load_permille)
        self.health_var.set(
            f"TEC {snapshot.tec}  ·  REC {snapshot.rec}  ·  Bus-Off {snapshot.bus_off}  ·  "
            f"攻击演示 {'开' if snapshot.demo else '关'}  ·  回环 {'开' if snapshot.loopback else '关'}"
        )
        self.can_topology.set_state(mode, snapshot.fps, snapshot.learned_ids, snapshot.score,
                                    snapshot.reason, snapshot.bus_off, snapshot.loopback)

    def _update_frame(self, frame: CanFrameSnapshot) -> None:
        frame_key = (frame.can_id, frame.fmt)
        previous_marker = self._last_frame_marker.get(frame_key)
        marker: tuple[object, ...]
        if frame.sequence is not None:
            marker = ("SEQ", frame.sequence)
        else:
            # Legacy fallback: payload/flags prevent two distinct frames in
            # the same millisecond from being collapsed unnecessarily.
            marker = (frame.timestamp_ms, frame.fd, frame.brs, frame.rtr, frame.dlc, frame.data,
                      frame.score, frame.reason)
        if previous_marker == marker:
            return
        previous_timestamp = self._last_frame_time.get(frame_key)
        count = self._frame_counts.get(frame_key, 0) + 1
        period_ms = (frame.timestamp_ms - previous_timestamp) if previous_timestamp is not None else 0
        self._frame_counts[frame_key] = count
        self._last_frame_marker[frame_key] = marker
        self._last_frame_time[frame_key] = frame.timestamp_ms
        frame_type = "CAN-FD"
        if frame.brs:
            frame_type += " + BRS"
        if not frame.fd:
            frame_type = "经典 CAN"
        data = frame.data.hex(" ").upper() or "—"
        values = (
            f"{frame.timestamp_ms / 1000:.3f}s",
            f"0x{frame.can_id:08X}",
            frame.fmt,
            frame_type,
            frame.dlc,
            data,
            count,
            f"{period_ms} ms" if period_ms else "—",
            frame.score,
            " · ".join(reason_labels(frame.reason)) or "正常",
        )
        existing = self._frame_rows.get(frame_key)
        tag = score_tag(frame.score)
        if existing and self.frames_tree.exists(existing):
            self.frames_tree.item(existing, values=values, tags=(tag,))
            self.frames_tree.move(existing, "", 0)
        else:
            item = self.frames_tree.insert("", 0, values=values, tags=(tag,))
            self._frame_rows[frame_key] = item
        self._trim_tree(self.frames_tree, 150)

    def _update_event(self, message: ProtocolMessage) -> None:
        timestamp_ms = message.get_int("T_MS", 0) or 0
        can_id = message.get_int("ID", 0) or 0
        dlc = message.get_int("DLC", 0) or 0
        score = message.get_int("SCORE", 0) or 0
        reason = message.get_int("REASON", 0) or 0
        key = f"{timestamp_ms}:{can_id}:{dlc}:{score}:{reason}"
        if key in self._event_key_set:
            return
        if len(self._event_keys) == self._event_keys.maxlen and self._event_keys:
            self._event_key_set.discard(self._event_keys[0])
        self._event_keys.append(key)
        self._event_key_set.add(key)
        values = (
            f"T+{timestamp_ms / 1000:.3f}s",
            "实时" if message.kind is MessageKind.EVENT else "历史",
            f"0x{can_id:08X}",
            dlc,
            score,
            " · ".join(reason_labels(reason)) or "未指定",
            f"0x{reason:02X}",
        )
        self.events_tree.insert("", 0, values=values, tags=(score_tag(score),))
        self._trim_tree(self.events_tree, MAX_TABLE_ROWS)
        if message.kind is MessageKind.EVENT:
            for label in reason_labels(reason):
                self._reason_counts[label] = self._reason_counts.get(label, 0) + 1
            self.reason_donut.set_counts(self._reason_counts)

    def _update_profile(self, message: ProtocolMessage) -> None:
        index = message.get("INDEX", "?") or "?"
        can_id = message.get_int("ID", 0) or 0
        period = message.get_int("PERIOD_US", 0) or 0
        rate_x10 = message.get_int("RATE_X10", None)
        if rate_x10 is None and period:
            rate_x10 = int(10_000_000 / period)
        risk = message.get_int("RISK", 0) or 0
        values = (
            index,
            f"0x{can_id:08X}",
            message.get("FMT", "STD"),
            message.get_int("DLC", 0) or 0,
            message.get_int("N", 0) or 0,
            f"{period / 1000:.2f} ms" if period else "—",
            f"{(rate_x10 or 0) / 10:.1f} Hz" if rate_x10 else "—",
            risk,
        )
        row_key = f"{can_id}:{message.get('FMT', 'STD')}"
        existing = self._profile_rows.get(row_key)
        tag = score_tag(min(1000, risk * 10))
        if existing and self.profiles_tree.exists(existing):
            self.profiles_tree.item(existing, values=values, tags=(tag,))
        else:
            item = self.profiles_tree.insert("", "end", values=values, tags=(tag,))
            self._profile_rows[row_key] = item

    def _merge_legacy_status(self, message: ProtocolMessage) -> None:
        if message.kind is MessageKind.MODEL:
            mode = message.get("STATE", "UNKNOWN") or "UNKNOWN"
            self.mode_var.set(_mode_cn(mode))
            return
        if message.kind is MessageKind.DIAG:
            mode = message.get("MODE", self.mode_var.get()) or self.mode_var.get()
            self.mode_var.set(_mode_cn(mode))
            fps = message.get_int("FPS", 0) or 0
            load = message.get_int("LOAD_PM", 0) or 0
            ids = message.get_int("IDS", 0) or 0
            self.cards["fps"].set(fps)
            self.cards["load"].set(f"{load / 10:.1f}")
            self.cards["ids"].set(ids)
        elif message.kind is MessageKind.AI:
            self.cards["total"].set(human_count(message.get_int("TOTAL", 0) or 0))
            self.cards["anomaly"].set(message.get_int("ANOMALY", 0) or 0)
        elif message.kind is MessageKind.CAN:
            self.cards["drops"].set(message.get_int("DROP", 0) or 0)
            self.health_var.set(
                f"TEC {message.get_int('TEC', 0) or 0}  ·  REC {message.get_int('REC', 0) or 0}  ·  "
                f"Bus-Off {message.get_int('BUSOFF', 0) or 0}"
            )

    # ---------------------------------------------------------- persistence
    def toggle_recording(self) -> None:
        if self.recorder.recording:
            saved = self.recorder.path
            try:
                self.recorder.stop()
            except OSError as error:
                self._log_local(f"关闭录制文件失败：{error}")
            self._capture_enabled = False
            self.record_var.set("开始录制")
            self._log_local(f"录制已停止：{saved or '仅内存'}")
            return
        default = f"ra8d1_edge_ai_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        path = filedialog.asksaveasfilename(title="录制 RA8D1 会话", defaultextension=".jsonl",
                                            initialfile=default,
                                            filetypes=(("RA8D1 JSONL", "*.jsonl"), ("所有文件", "*.*")))
        if not path:
            return
        try:
            self.recorder.start(path)
        except OSError as error:
            messagebox.showerror("录制启动失败", str(error))
            return
        self._capture_enabled = True
        self.record_var.set("停止录制")
        self._log_local(f"已开始录制：{path}")

    def export_session(self) -> None:
        if not self.recorder.count:
            messagebox.showinfo("导出会话", "当前会话还没有已录制的数据。请先开始录制。")
            return
        path = filedialog.asksaveasfilename(title="导出会话 CSV", defaultextension=".csv",
                                            initialfile=f"ra8d1_session_{datetime.now():%Y%m%d_%H%M%S}.csv",
                                            filetypes=(("CSV", "*.csv"),))
        if path:
            self.recorder.export_csv(path)
            self._log_local(f"已导出：{path}")

    def export_events(self) -> None:
        if not self.recorder.count:
            messagebox.showinfo("导出事件", "请先在“原始协议”页开始录制，然后导出事件。")
            return
        path = filedialog.asksaveasfilename(title="导出异常事件 CSV", defaultextension=".csv",
                                            initialfile=f"ra8d1_anomalies_{datetime.now():%Y%m%d_%H%M%S}.csv",
                                            filetypes=(("CSV", "*.csv"),))
        if path:
            self.recorder.export_csv(path, kinds=(MessageKind.EVENT, MessageKind.LOG))
            self._log_local(f"异常事件已导出：{path}")

    # --------------------------------------------------------------- helpers
    def _set_connection_status(self, text: str, online: bool, *, demo: bool = False) -> None:
        self.status_var.set(text)
        if online:
            color = COLORS["purple"] if demo else COLORS["green"]
            self.status_badge.configure(bg="#172F36" if not demo else "#292345", fg=color)
        else:
            self.status_badge.configure(bg="#35212A", fg=COLORS["red"])

    def _append_console(self, line: str, kind: MessageKind = MessageKind.TEXT) -> None:
        if not line:
            return
        self.console.configure(state="normal")
        color = {
            MessageKind.EVENT: COLORS["red"], MessageKind.TELEM: COLORS["cyan"],
            MessageKind.FRAME: COLORS["blue"], MessageKind.PROFILE: COLORS["purple"],
            MessageKind.INVALID: COLORS["amber"], MessageKind.UNKNOWN: COLORS["amber"],
        }.get(kind, "#AFC8DC")
        tag = f"kind_{kind.value}"
        self.console.tag_configure(tag, foreground=color)
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.console.insert("end", f"{stamp}  {line}\n", tag)
        self._console_lines += 1
        if self._console_lines > MAX_CONSOLE_LINES:
            self.console.delete("1.0", "201.0")
            self._console_lines -= 200
        self.console.see("end")
        self.console.configure(state="disabled")

    def _log_local(self, text: str) -> None:
        self._append_console(f"# {text}", MessageKind.TEXT)

    def _clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        self._console_lines = 0

    @staticmethod
    def _trim_tree(tree: ttk.Treeview, limit: int) -> None:
        children = tree.get_children()
        for item in children[limit:]:
            tree.delete(item)

    def _reset_views(self) -> None:
        self.timeline.clear()
        self.gauge.set_score(0)
        self.reason_var.set("当前未检测到异常")
        self._profile_rows.clear()
        self._frame_rows.clear()
        self._frame_counts.clear()
        self._last_frame_marker.clear()
        self._last_frame_time.clear()
        self._event_keys.clear()
        self._event_key_set.clear()
        self._reason_counts = {label: 0 for label in reason_labels(0x7F)}
        self.reason_donut.clear()
        self.can_topology.set_state("等待数据", 0, 0, 0, 0, 0, False)
        for tree in (self.frames_tree, self.events_tree, self.profiles_tree):
            tree.delete(*tree.get_children())
        if hasattr(self, "bmi_dashboard"):
            self.bmi_dashboard.reset()

    def close(self) -> None:
        self._closing = True
        if self.recorder.recording:
            try:
                self.recorder.stop()
            except OSError:
                pass
        self._capture_enabled = False
        self.disconnect()
        self.stop_replay()
        self.root.destroy()


def create_app(*, root: tk.Tk | None = None, port: str | None = None, baud: int = 115200,
               demo: bool | str = False,
               replay: str | None = None) -> tuple[tk.Tk, EdgeIdsStudio]:
    root = root or tk.Tk()
    return root, EdgeIdsStudio(root, port=port, baud=baud, demo=demo, replay=replay)
