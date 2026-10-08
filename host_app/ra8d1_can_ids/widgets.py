"""Small dependency-free dashboard widgets for the host application."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
import math
import tkinter as tk
from tkinter import ttk


COLORS = {
    "bg": "#07111F",
    "surface": "#0D1A2B",
    "surface_alt": "#122238",
    "surface_hover": "#19304B",
    "border": "#223A55",
    "text": "#E8F1FA",
    "muted": "#8FA6BC",
    "cyan": "#27D3F2",
    "blue": "#4C8DFF",
    "green": "#35D49A",
    "amber": "#FFBD4A",
    "red": "#FF6178",
    "purple": "#B58CFF",
}

UI_FONT = "Microsoft YaHei UI"
NUM_FONT = "Segoe UI"
MONO_FONT = "Cascadia Mono"
CAPTION_SIZE = 8
BODY_SIZE = 9


def apply_theme(root: tk.Misc) -> ttk.Style:
    """Apply a compact dark industrial theme and return its ttk style."""

    root.configure(background=COLORS["bg"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=COLORS["bg"], foreground=COLORS["text"],
                    fieldbackground=COLORS["surface"], bordercolor=COLORS["border"],
                    lightcolor=COLORS["border"], darkcolor=COLORS["border"],
                    font=(UI_FONT, BODY_SIZE))
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("Card.TFrame", background=COLORS["surface"], relief="flat")
    style.configure("Header.TFrame", background=COLORS["surface_alt"])
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("Surface.TLabel", background=COLORS["surface"], foreground=COLORS["text"])
    style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"])
    style.configure("SurfaceMuted.TLabel", background=COLORS["surface"], foreground=COLORS["muted"])
    style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"],
                    font=(UI_FONT, 18, "bold"))
    style.configure("Section.TLabel", background=COLORS["bg"], foreground=COLORS["text"],
                    font=(UI_FONT, 11, "bold"))
    style.configure("CardValue.TLabel", background=COLORS["surface"], foreground=COLORS["text"],
                    font=(NUM_FONT, 22, "bold"))
    style.configure("CardUnit.TLabel", background=COLORS["surface"], foreground=COLORS["muted"],
                    font=(UI_FONT, 8))
    style.configure("TButton", background=COLORS["surface_alt"], foreground=COLORS["text"],
                    borderwidth=1, padding=(10, 7), focusthickness=0)
    style.map("TButton",
              background=[("active", COLORS["surface_hover"]), ("pressed", COLORS["blue"])],
              foreground=[("disabled", COLORS["muted"])])
    style.configure("Accent.TButton", background=COLORS["blue"], foreground="#FFFFFF",
                    font=(UI_FONT, 9, "bold"))
    style.map("Accent.TButton", background=[("active", "#68A1FF"), ("pressed", "#3378E8")])
    style.configure("Danger.TButton", background="#5A2633", foreground="#FFDDE3")
    style.map("Danger.TButton", background=[("active", "#793044")])
    style.configure("TEntry", fieldbackground=COLORS["surface"], foreground=COLORS["text"],
                    insertcolor=COLORS["text"], padding=7)
    style.configure("TCombobox", fieldbackground=COLORS["surface"], foreground=COLORS["text"],
                    arrowcolor=COLORS["muted"], padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["surface"])],
              selectbackground=[("readonly", COLORS["surface"])],
              selectforeground=[("readonly", COLORS["text"])])
    style.configure("TNotebook", background=COLORS["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=COLORS["bg"], foreground=COLORS["muted"],
                    padding=(15, 9), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", COLORS["surface_alt"])],
              foreground=[("selected", COLORS["cyan"]), ("active", COLORS["text"])])
    style.configure("Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"],
                    foreground=COLORS["text"], rowheight=28, borderwidth=0)
    style.configure("Treeview.Heading", background=COLORS["surface_alt"], foreground=COLORS["muted"],
                    relief="flat", font=(UI_FONT, 8, "bold"), padding=(7, 7))
    style.map("Treeview", background=[("selected", "#1C4B73")], foreground=[("selected", "#FFFFFF")])
    style.map("Treeview.Heading", background=[("active", COLORS["surface_hover"])])
    style.configure("Vertical.TScrollbar", background=COLORS["surface_alt"], troughcolor=COLORS["bg"],
                    arrowcolor=COLORS["muted"], borderwidth=0)
    style.configure("Horizontal.TScrollbar", background=COLORS["surface_alt"], troughcolor=COLORS["bg"],
                    arrowcolor=COLORS["muted"], borderwidth=0)
    style.configure("TCheckbutton", background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("TRadiobutton", background=COLORS["bg"], foreground=COLORS["text"])
    return style


class MetricCard(ttk.Frame):
    """A title/value/unit KPI card with a colored left marker."""

    def __init__(self, master: tk.Misc, title: str, value: str = "--", unit: str = "",
                 accent: str | None = None, subtitle: str = "") -> None:
        super().__init__(master, style="Card.TFrame", padding=(14, 11))
        self._accent = accent or COLORS["cyan"]
        marker = tk.Frame(self, background=self._accent, width=3, height=52)
        marker.grid(row=0, column=0, rowspan=3, sticky="ns", padx=(0, 11))
        marker.grid_propagate(False)
        ttk.Label(self, text=title, style="SurfaceMuted.TLabel",
                  font=(UI_FONT, CAPTION_SIZE, "bold")).grid(row=0, column=1, sticky="w")
        value_row = ttk.Frame(self, style="Card.TFrame")
        value_row.grid(row=1, column=1, sticky="w", pady=(1, 0))
        self._value = ttk.Label(value_row, text=value, style="CardValue.TLabel")
        self._value.pack(side="left")
        self._unit = ttk.Label(value_row, text=(" " + unit if unit else ""), style="CardUnit.TLabel")
        self._unit.pack(side="left", anchor="s", pady=(0, 4))
        self._subtitle = ttk.Label(self, text=subtitle, style="SurfaceMuted.TLabel",
                                   font=(UI_FONT, CAPTION_SIZE))
        self._subtitle.grid(row=2, column=1, sticky="w")
        self.columnconfigure(1, weight=1)

    def set(self, value: object, subtitle: str | None = None, unit: str | None = None) -> None:
        self._value.configure(text=str(value))
        if subtitle is not None:
            self._subtitle.configure(text=subtitle)
        if unit is not None:
            self._unit.configure(text=(" " + unit if unit else ""))


class ScoreGauge(tk.Canvas):
    """Semicircular 0..1000 anomaly score gauge."""

    def __init__(self, master: tk.Misc, width: int = 260, height: int = 155) -> None:
        super().__init__(master, width=width, height=height, background=COLORS["surface"],
                         highlightthickness=0)
        self._score = 0
        self.bind("<Configure>", lambda _event: self._draw())
        self._draw()

    def set_score(self, score: int) -> None:
        self._score = max(0, min(1000, int(score)))
        self._draw()

    @staticmethod
    def _score_color(score: int) -> str:
        if score >= 700:
            return COLORS["red"]
        if score >= 350:
            return COLORS["amber"]
        return COLORS["green"]

    def _draw(self) -> None:
        self.delete("all")
        width = max(180, self.winfo_width())
        height = max(120, self.winfo_height())
        pad = 24
        diameter = min(width - (pad * 2), (height - 25) * 2)
        x0 = (width - diameter) / 2
        y0 = 20
        x1 = x0 + diameter
        y1 = y0 + diameter
        self.create_arc(x0, y0, x1, y1, start=0, extent=180, style="arc",
                        outline=COLORS["border"], width=14)
        extent = 180.0 * (self._score / 1000.0)
        if extent > 0:
            self.create_arc(x0, y0, x1, y1, start=180 - extent, extent=extent, style="arc",
                            outline=self._score_color(self._score), width=14)
        center_x = width / 2
        baseline_y = y0 + (diameter / 2) + 5
        self.create_text(center_x, baseline_y - 23, text=str(self._score), fill=COLORS["text"],
                         font=(NUM_FONT, 27, "bold"))
        self.create_text(center_x, baseline_y + 8, text="异常分数 / 1000", fill=COLORS["muted"],
                         font=(UI_FONT, 7, "bold"))
        self.create_text(x0 + 3, baseline_y + 6, text="0", fill=COLORS["muted"], anchor="w",
                         font=(NUM_FONT, 8))
        self.create_text(x1 - 3, baseline_y + 6, text="1000", fill=COLORS["muted"], anchor="e",
                         font=(NUM_FONT, 8))


class TimelineChart(tk.Canvas):
    """Rolling score/load chart implemented with the Tk canvas."""

    def __init__(self, master: tk.Misc, max_points: int = 180, height: int = 250) -> None:
        super().__init__(master, height=height, background=COLORS["surface"], highlightthickness=0)
        self._points: deque[tuple[float, int, int]] = deque(maxlen=max_points)
        self.bind("<Configure>", lambda _event: self._draw())

    def add_point(self, timestamp: float, score: int, load_permille: int) -> None:
        self._points.append((float(timestamp), max(0, min(1000, int(score))),
                             max(0, min(1000, int(load_permille)))))
        self._draw()

    def clear(self) -> None:
        self._points.clear()
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(260, self.winfo_width())
        height = max(160, self.winfo_height())
        left, top, right, bottom = 45, 28, width - 18, height - 28
        plot_w, plot_h = right - left, bottom - top
        for index in range(5):
            y = top + (plot_h * index / 4)
            value = 1000 - (index * 250)
            self.create_line(left, y, right, y, fill=COLORS["border"], dash=(2, 4))
            self.create_text(left - 8, y, text=str(value), fill=COLORS["muted"], anchor="e",
                             font=(NUM_FONT, 7))
        self.create_text(left, 11, text="端侧 AI 实时推理", fill=COLORS["muted"], anchor="w",
                         font=(UI_FONT, 7, "bold"))
        self.create_line(right - 156, 11, right - 140, 11, fill=COLORS["red"], width=3)
        self.create_text(right - 134, 11, text="异常分数", fill=COLORS["muted"], anchor="w",
                         font=(UI_FONT, 7))
        self.create_line(right - 75, 11, right - 59, 11, fill=COLORS["cyan"], width=3)
        self.create_text(right - 53, 11, text="总线负载", fill=COLORS["muted"], anchor="w",
                         font=(UI_FONT, 7))
        if len(self._points) < 2:
            self.create_text((left + right) / 2, (top + bottom) / 2,
                             text="等待设备遥测数据…", fill=COLORS["muted"],
                             font=(UI_FONT, 9))
            return
        points = list(self._points)
        first_ts, last_ts = points[0][0], points[-1][0]
        span = max(1.0, last_ts - first_ts)
        score_coords: list[float] = []
        load_coords: list[float] = []
        for timestamp, score, load in points:
            x = left + ((timestamp - first_ts) / span * plot_w)
            score_coords.extend((x, bottom - (score / 1000.0 * plot_h)))
            load_coords.extend((x, bottom - (load / 1000.0 * plot_h)))
        self.create_line(*load_coords, fill=COLORS["cyan"], width=2, smooth=True)
        self.create_line(*score_coords, fill=COLORS["red"], width=2, smooth=True)
        self.create_text(left, bottom + 15, text=f"-{span:.0f}s", fill=COLORS["muted"], anchor="w",
                         font=(NUM_FONT, 7))
        self.create_text(right, bottom + 15, text="现在", fill=COLORS["muted"], anchor="e",
                         font=(UI_FONT, 7))


def _bounded_int(value: object, lower: int, upper: int, default: int = 0) -> int:
    """Convert telemetry values without allowing malformed input to break drawing."""

    try:
        number = float(value)
        if not math.isfinite(number):
            return default
        converted = int(round(number))
    except (TypeError, ValueError, OverflowError):
        return default
    return max(lower, min(upper, converted))


class BmiTrendChart(tk.Canvas):
    """Rolling BMI088 score, temperature and confidence trend chart.

    The three signals keep their firmware-native ranges: anomaly score is
    0..2500 (score x100), temperature is 0..100000 millidegrees Celsius and
    confidence is 0..1000 per mille.  They share a normalized plot area while
    both axes and the legend retain the real units.
    """

    SCORE_MAX = 2500
    TEMPERATURE_MAX_MC = 100_000
    CONFIDENCE_MAX_PM = 1000

    def __init__(self, master: tk.Misc, max_points: int = 180, height: int = 270) -> None:
        super().__init__(master, height=height, background=COLORS["surface"], highlightthickness=0)
        self._points: deque[tuple[float, int, int, int]] = deque(maxlen=max(2, int(max_points)))
        self.bind("<Configure>", lambda _event: self._draw())

    def add_point(self, timestamp: float, score_x100: int, temp_mc: int,
                  confidence_pm: int) -> None:
        """Append one native-unit snapshot and redraw the rolling window."""

        try:
            safe_timestamp = float(timestamp)
            if not math.isfinite(safe_timestamp):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            safe_timestamp = (self._points[-1][0] + 1.0) if self._points else 0.0
        self._points.append((
            safe_timestamp,
            _bounded_int(score_x100, 0, self.SCORE_MAX),
            _bounded_int(temp_mc, 0, self.TEMPERATURE_MAX_MC),
            _bounded_int(confidence_pm, 0, self.CONFIDENCE_MAX_PM),
        ))
        self._draw()

    def clear(self) -> None:
        self._points.clear()
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(340, self.winfo_width())
        height = max(205, self.winfo_height())
        left, top, right, bottom = 58, 52, width - 72, height - 30
        plot_w, plot_h = max(1, right - left), max(1, bottom - top)

        self.create_text(left, 13, text="BMI088 端侧 AI 趋势", fill=COLORS["muted"], anchor="w",
                         font=(UI_FONT, 7, "bold"))
        latest = self._points[-1] if self._points else (0.0, 0, 0, 0)
        legends = (
            (COLORS["red"], f"异常分数 {latest[1]} / 2500"),
            (COLORS["amber"], f"温度 {latest[2] / 1000.0:.1f} ℃"),
            (COLORS["purple"], f"置信度 {latest[3] / 10.0:.1f}%"),
        )
        legend_x = left
        for color, label in legends:
            self.create_line(legend_x, 34, legend_x + 15, 34, fill=color, width=3)
            self.create_text(legend_x + 20, 34, text=label, fill=COLORS["muted"], anchor="w",
                             font=(UI_FONT, 7))
            legend_x += max(105, len(label) * 6 + 35)

        for index in range(5):
            fraction = 1.0 - (index / 4.0)
            y = top + (plot_h * index / 4.0)
            self.create_line(left, y, right, y, fill=COLORS["border"], dash=(2, 5))
            self.create_text(left - 7, y, text=str(round(self.SCORE_MAX * fraction)),
                             fill=COLORS["muted"], anchor="e", font=(NUM_FONT, 7))
            self.create_text(right + 7, y, text=f"{round(100 * fraction)} ℃ / {round(100 * fraction)}%",
                             fill=COLORS["muted"], anchor="w", font=(UI_FONT, 7))

        def threshold(value_fraction: float, label: str, color: str, offset: int = 0) -> None:
            y = bottom - (value_fraction * plot_h)
            self.create_line(left, y, right, y, fill=color, dash=(6, 4))
            self.create_text(right - 4, y + offset, text=label, fill=color, anchor="se",
                             font=(UI_FONT, 6, "bold"))

        threshold(900 / self.SCORE_MAX, "分数报警 9.00", "#7B3043", -2)
        threshold(0.60, "温度预警 60 ℃", "#866523", -2)
        threshold(0.70, "温度报警 70 ℃ / 置信度 70%", "#774052", -2)

        if not self._points:
            self.create_text((left + right) / 2, (top + bottom) / 2,
                             text="等待 BMI088 遥测数据…", fill=COLORS["muted"],
                             font=(UI_FONT, 9))
            return

        points = list(self._points)
        timestamps = [item[0] for item in points]
        first_ts, last_ts = min(timestamps), max(timestamps)
        span = last_ts - first_ts

        def x_at(index: int, timestamp_value: float) -> float:
            if span > 1.0e-9:
                return left + ((timestamp_value - first_ts) / span * plot_w)
            if len(points) > 1:
                return left + (index / (len(points) - 1) * plot_w)
            return right

        series: tuple[tuple[int, float, str], ...] = (
            (1, float(self.SCORE_MAX), COLORS["red"]),
            (2, float(self.TEMPERATURE_MAX_MC), COLORS["amber"]),
            (3, float(self.CONFIDENCE_MAX_PM), COLORS["purple"]),
        )
        for field_index, maximum, color in series:
            coordinates: list[float] = []
            for index, point in enumerate(points):
                coordinates.extend((x_at(index, point[0]), bottom - (point[field_index] / maximum * plot_h)))
            if len(points) == 1:
                self.create_oval(coordinates[0] - 2, coordinates[1] - 2,
                                 coordinates[0] + 2, coordinates[1] + 2,
                                 fill=color, outline=color)
            else:
                self.create_line(*coordinates, fill=color, width=2, smooth=True)

        shown_span = max(0.0, last_ts - first_ts)
        self.create_text(left, bottom + 15, text=f"-{shown_span:.1f}s", fill=COLORS["muted"], anchor="w",
                         font=(NUM_FONT, 7))
        self.create_text(right, bottom + 15, text="现在", fill=COLORS["muted"], anchor="e",
                         font=(UI_FONT, 7))


class WaveformChart(tk.Canvas):
    """Display a normalized 64-point BMI088 vibration waveform (-100..100)."""

    POINT_COUNT = 64

    def __init__(self, master: tk.Misc, height: int = 250) -> None:
        super().__init__(master, height=height, background=COLORS["surface"], highlightthickness=0)
        self._samples: tuple[int, ...] = ()
        self.bind("<Configure>", lambda _event: self._draw())

    def set_samples(self, sequence: Sequence[int]) -> None:
        """Set samples, downsampling longer future payloads to 64 points."""

        if isinstance(sequence, (str, bytes, bytearray)):
            values: list[object] = []
        else:
            try:
                values = list(sequence)
            except TypeError:
                values = []
        if len(values) > self.POINT_COUNT:
            last = len(values) - 1
            values = [values[round(index * last / (self.POINT_COUNT - 1))]
                      for index in range(self.POINT_COUNT)]
        self._samples = tuple(_bounded_int(value, -100, 100) for value in values)
        self._draw()

    def clear(self) -> None:
        self._samples = ()
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(300, self.winfo_width())
        height = max(190, self.winfo_height())
        left, top, right, bottom = 45, 34, width - 18, height - 28
        plot_w, plot_h = max(1, right - left), max(1, bottom - top)
        self.create_text(left, 13, text="加速度幅值 / 64 点波形",
                         fill=COLORS["muted"], anchor="w",
                         font=(UI_FONT, 7, "bold"))

        for value in (100, 50, 0, -50, -100):
            y = top + ((100 - value) / 200.0 * plot_h)
            zero = value == 0
            self.create_line(left, y, right, y,
                             fill=COLORS["cyan"] if zero else COLORS["border"],
                             width=1 if not zero else 2,
                             dash=() if zero else (2, 5))
            self.create_text(left - 7, y, text=str(value), fill=COLORS["muted"], anchor="e",
                             font=(NUM_FONT, 7))
        for sample_index in (0, 16, 32, 48, 63):
            x = left + (sample_index / (self.POINT_COUNT - 1) * plot_w)
            self.create_line(x, top, x, bottom, fill=COLORS["border"], dash=(2, 6))
            self.create_text(x, bottom + 15, text=str(sample_index), fill=COLORS["muted"],
                             anchor="center", font=(NUM_FONT, 7))

        if not self._samples:
            self.create_text((left + right) / 2, (top + bottom) / 2,
                             text="等待振动波形…", fill=COLORS["muted"],
                             font=(UI_FONT, 9))
            return

        count = len(self._samples)
        coordinates: list[float] = []
        for index, sample in enumerate(self._samples):
            x = left + ((index / max(1, count - 1)) * plot_w)
            y = top + ((100 - sample) / 200.0 * plot_h)
            coordinates.extend((x, y))
        if count == 1:
            self.create_oval(coordinates[0] - 3, coordinates[1] - 3,
                             coordinates[0] + 3, coordinates[1] + 3,
                             fill=COLORS["blue"], outline=COLORS["blue"])
        else:
            self.create_line(*coordinates, fill=COLORS["blue"], width=2, smooth=True)
        self.create_text(right, top + 5,
                         text=f"最小 {min(self._samples):+d}   最大 {max(self._samples):+d}",
                         fill=COLORS["blue"], anchor="ne", font=(UI_FONT, 7, "bold"))


class ExplanationBars(tk.Canvas):
    """Top-three one-class feature contributions in native score-x100 units."""

    CONTRIBUTION_MAX = 2500
    ITEM_COUNT = 3

    def __init__(self, master: tk.Misc, height: int = 230) -> None:
        super().__init__(master, height=height, background=COLORS["surface"], highlightthickness=0)
        self._items: tuple[tuple[str, int], ...] = ()
        self.bind("<Configure>", lambda _event: self._draw())

    def set_items(self, sequence: Sequence[tuple[str, int]]) -> None:
        """Set up to three ranked items while tolerating incomplete records."""

        parsed: list[tuple[str, int]] = []
        if not isinstance(sequence, (str, bytes, bytearray)):
            try:
                candidates = iter(sequence)
            except TypeError:
                candidates = iter(())
            for candidate in candidates:
                if len(parsed) >= self.ITEM_COUNT:
                    break
                try:
                    name, contribution = candidate[0], candidate[1]
                except (TypeError, IndexError, KeyError):
                    continue
                label = str(name).strip() or "未知特征"
                parsed.append((label, _bounded_int(contribution, 0, self.CONTRIBUTION_MAX)))
        self._items = tuple(parsed)
        self._draw()

    def clear(self) -> None:
        self._items = ()
        self._draw()

    @staticmethod
    def _short_name(name: str, limit: int = 24) -> str:
        return name if len(name) <= limit else name[:limit - 1] + "…"

    def _draw(self) -> None:
        self.delete("all")
        width = max(340, self.winfo_width())
        height = max(205, self.winfo_height())
        left, right = 145, width - 26
        bar_w = max(1, right - left)
        self.create_text(16, 15, text="异常贡献度 TOP 3", fill=COLORS["muted"], anchor="w",
                         font=(UI_FONT, 7, "bold"))
        self.create_text(right, 15, text="0 — 25.00 z²", fill=COLORS["muted"], anchor="e",
                         font=(NUM_FONT, 7))

        if not self._items:
            self.create_text(width / 2, height / 2, text="等待模型解释数据…",
                             fill=COLORS["muted"], font=(UI_FONT, 9))
            return

        row_gap = min(61, max(48, (height - 46) // self.ITEM_COUNT))
        colors = (COLORS["red"], COLORS["amber"], COLORS["purple"])
        for rank, (name, contribution) in enumerate(self._items):
            y = 48 + (rank * row_gap)
            self.create_text(16, y + 8, text=f"{rank + 1}  {self._short_name(name)}",
                             fill=COLORS["text"], anchor="w", font=(UI_FONT, 8, "bold"))
            self.create_rectangle(left, y, right, y + 17, fill=COLORS["border"], outline="")
            fill_right = left + (bar_w * contribution / self.CONTRIBUTION_MAX)
            if fill_right > left:
                self.create_rectangle(left, y, fill_right, y + 17, fill=colors[rank], outline="")
            self.create_text(right, y + 25, text=f"{contribution / 100.0:.2f}  ({contribution})",
                             fill=colors[rank], anchor="e", font=(NUM_FONT, 7, "bold"))


def _bounded_float(value: object, lower: float = 0.0, upper: float = 1.0e30,
                   default: float = 0.0) -> float:
    """Return a finite, bounded float suitable for plotting."""

    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(converted):
        return default
    return max(lower, min(upper, converted))


def _telemetry_bool(value: object) -> bool:
    """Understand the common textual and numeric boolean telemetry forms."""

    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {"0", "OFF", "FALSE", "NO", "NONE", "DISABLED"}:
            return False
        if normalized in {"1", "ON", "TRUE", "YES", "ENABLED", "BUS_OFF"}:
            return True
    try:
        return bool(int(value))
    except (TypeError, ValueError, OverflowError):
        return bool(value)


class CanBusTopology(tk.Canvas):
    """Animated PC-to-CAN topology for the CAN edge-IDS system page."""

    def __init__(self, master: tk.Misc, height: int = 310) -> None:
        super().__init__(master, height=height, background=COLORS["surface"], highlightthickness=0)
        self._mode = "等待设备"
        self._fps = 0
        self._learned_ids = 0
        self._score = 0
        self._reason_mask = 0
        self._bus_off = False
        self._loopback = False
        self._phase = 0.0
        self._animation_job: str | None = None
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._schedule_animation()

    def set_state(self, mode: object, fps: object, learned_ids: object, score: object,
                  reason_mask: object, bus_off: object, loopback: object) -> None:
        """Update topology telemetry; malformed device values degrade to safe defaults."""

        raw_mode = str(mode or "").strip().upper()
        self._mode = {
            "LEARNING": "学习基线",
            "LEARN": "学习基线",
            "MONITORING": "实时监测",
            "MONITOR": "实时监测",
            "IDLE": "空闲",
            "DEMO": "演示模式",
            "ERROR": "设备异常",
        }.get(raw_mode, str(mode).strip() if str(mode).strip() else "等待设备")
        self._fps = _bounded_int(fps, 0, 1_000_000)
        self._learned_ids = _bounded_int(learned_ids, 0, 65_535)
        self._score = _bounded_int(score, 0, 1000)
        try:
            if isinstance(reason_mask, str):
                self._reason_mask = max(0, min(0xFFFFFFFF, int(reason_mask.strip(), 0)))
            else:
                self._reason_mask = max(0, min(0xFFFFFFFF, int(reason_mask)))
        except (TypeError, ValueError, OverflowError):
            self._reason_mask = 0
        self._bus_off = _telemetry_bool(bus_off)
        self._loopback = _telemetry_bool(loopback)
        self._draw()

    def _schedule_animation(self) -> None:
        if self._animation_job is None:
            self._animation_job = self.after(120, self._animate)

    def _animate(self) -> None:
        self._animation_job = None
        try:
            if not self.winfo_exists():
                return
            self._phase = (self._phase + 0.075) % 1.0
            if self.winfo_ismapped() and self._fps > 0:
                self._draw()
            self._schedule_animation()
        except tk.TclError:
            return

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self and self._animation_job is not None:
            try:
                self.after_cancel(self._animation_job)
            except tk.TclError:
                pass
            self._animation_job = None

    @staticmethod
    def _health_color(score: int, reason_mask: int, bus_off: bool) -> str:
        if bus_off or score >= 700:
            return COLORS["red"]
        if reason_mask or score >= 350:
            return COLORS["amber"]
        return COLORS["green"]

    @staticmethod
    def _reason_text(reason_mask: int, bus_off: bool) -> str:
        reasons: list[str] = []
        if reason_mask & 0x01:
            reasons.append("未知 ID")
        if reason_mask & 0x02:
            reasons.append("周期异常")
        if reason_mask & 0x04:
            reasons.append("洪泛流量")
        if reason_mask & 0x08:
            reasons.append("DLC 变化")
        if reason_mask & 0x10:
            reasons.append("载荷跳变")
        if reason_mask & 0x20:
            reasons.append("总线故障")
        if reason_mask & 0x40:
            reasons.append("模型已满")
        if bus_off:
            reasons.append("Bus-Off")
        return "、".join(reasons) if reasons else "总线健康"

    def _box(self, center_x: float, center_y: float, box_w: float, box_h: float,
             title: str, subtitle: str, accent: str) -> None:
        x0, y0 = center_x - box_w / 2, center_y - box_h / 2
        x1, y1 = center_x + box_w / 2, center_y + box_h / 2
        self.create_rectangle(x0, y0, x1, y1, fill=COLORS["surface_alt"],
                              outline=accent, width=2)
        self.create_rectangle(x0, y0, x0 + 4, y1, fill=accent, outline="")
        self.create_text(center_x, center_y - 8, text=title, fill=COLORS["text"],
                         font=(UI_FONT, 9, "bold"))
        self.create_text(center_x, center_y + 12, text=subtitle, fill=COLORS["muted"],
                         font=(UI_FONT, 7))

    def _flow_dots(self, x0: float, y0: float, x1: float, y1: float, color: str,
                   count: int = 3) -> None:
        if self._fps <= 0:
            return
        for index in range(count):
            fraction = (self._phase + (index / count)) % 1.0
            x = x0 + ((x1 - x0) * fraction)
            y = y0 + ((y1 - y0) * fraction)
            radius = 3 if index else 4
            self.create_oval(x - radius, y - radius, x + radius, y + radius,
                             fill=color, outline="")

    def _draw(self) -> None:
        self.delete("all")
        width = max(430, self.winfo_width())
        height = max(280, self.winfo_height())
        health = self._health_color(self._score, self._reason_mask, self._bus_off)

        self.create_text(16, 15, text="CAN 端侧智能监测拓扑", fill=COLORS["muted"],
                         anchor="w", font=(UI_FONT, 8, "bold"))
        self.create_text(width - 16, 15,
                         text=f"{self._mode}  ·  {self._fps} 帧/秒  ·  异常分数 {self._score}",
                         fill=health, anchor="e", font=(UI_FONT, 8, "bold"))

        centers = (width * 0.15, width * 0.50, width * 0.85)
        box_w = min(150.0, max(92.0, (width - 100.0) / 3.0))
        center_y, box_h = 88.0, 62.0
        link_y = center_y
        self.create_line(centers[0] + box_w / 2, link_y, centers[1] - box_w / 2, link_y,
                         fill=COLORS["blue"], width=3, arrow="last")
        self.create_line(centers[1] + box_w / 2, link_y, centers[2] - box_w / 2, link_y,
                         fill=COLORS["cyan"], width=3, arrow="last")
        self._flow_dots(centers[0] + box_w / 2, link_y,
                        centers[1] - box_w / 2, link_y, COLORS["blue"], 2)
        self._flow_dots(centers[1] + box_w / 2, link_y,
                        centers[2] - box_w / 2, link_y, COLORS["cyan"], 2)
        self._box(centers[0], center_y, box_w, box_h, "PC 上位机", "串口遥测与控制", COLORS["blue"])
        self._box(centers[1], center_y, box_w, box_h, "RA8D1", "端侧 AI 异常检测", health)
        self._box(centers[2], center_y, box_w, box_h, "CAN 收发器",
                  "回环" if self._loopback else "物理总线", COLORS["cyan"])
        self.create_text((centers[0] + centers[1]) / 2, 63, text="UART 115200",
                         fill=COLORS["muted"], font=(NUM_FONT, 7))
        self.create_text((centers[1] + centers[2]) / 2, 63, text="CAN-FD 控制器",
                         fill=COLORS["muted"], font=(UI_FONT, 7))

        bus_left, bus_right = 35.0, width - 35.0
        can_h_y, can_l_y = 174.0, 190.0
        trans_bottom = center_y + box_h / 2
        self.create_line(centers[2], trans_bottom, centers[2], can_h_y,
                         fill=COLORS["cyan"], width=3)
        self.create_line(bus_left, can_h_y, bus_right, can_h_y, fill=COLORS["cyan"], width=3)
        self.create_line(bus_left, can_l_y, bus_right, can_l_y, fill=COLORS["blue"], width=3)
        self.create_line(bus_left, can_h_y - 8, bus_left, can_l_y + 8,
                         fill=COLORS["amber"], width=4)
        self.create_line(bus_right, can_h_y - 8, bus_right, can_l_y + 8,
                         fill=COLORS["amber"], width=4)
        self.create_text(bus_left + 4, can_h_y - 8, text="CAN_H", anchor="sw",
                         fill=COLORS["cyan"], font=(NUM_FONT, 7, "bold"))
        self.create_text(bus_left + 4, can_l_y + 8, text="CAN_L", anchor="nw",
                         fill=COLORS["blue"], font=(NUM_FONT, 7, "bold"))
        self._flow_dots(bus_left, can_h_y, bus_right, can_h_y, health, 5)

        node_y = min(height - 48.0, 239.0)
        node_centers = (width * 0.25, width * 0.50, width * 0.75)
        node_labels = ("车身 ECU", "动力 ECU", "传感器节点")
        for node_x, label in zip(node_centers, node_labels):
            self.create_line(node_x, can_l_y, node_x, node_y - 15, fill=COLORS["border"], width=2)
            self.create_rectangle(node_x - 44, node_y - 15, node_x + 44, node_y + 15,
                                  fill=COLORS["surface_alt"], outline=COLORS["border"])
            self.create_text(node_x, node_y, text=label, fill=COLORS["text"], font=(UI_FONT, 7))

        legend_y = height - 14
        status_text = self._reason_text(self._reason_mask, self._bus_off)
        self.create_oval(16, legend_y - 5, 26, legend_y + 5, fill=health, outline="")
        self.create_text(33, legend_y, text=status_text, fill=health, anchor="w",
                         font=(UI_FONT, 7, "bold"))
        self.create_text(width - 16, legend_y,
                         text=f"已学习 ID：{self._learned_ids}  ·  终端电阻 120Ω × 2",
                         fill=COLORS["muted"], anchor="e", font=(UI_FONT, 7))


class SpectrumBars(tk.Canvas):
    """Responsive 12-band vibration spectrum with dominant-band annotation."""

    FREQUENCIES: tuple[float, ...] = (12.5, 25, 50, 75, 100, 125, 150, 200,
                                      250, 300, 350, 390)

    def __init__(self, master: tk.Misc, height: int = 230) -> None:
        super().__init__(master, height=height, background=COLORS["surface"], highlightthickness=0)
        self._features: tuple[float, ...] = ()
        self.bind("<Configure>", lambda _event: self._draw())

    @classmethod
    def _frequency_from_key(cls, key: object) -> float | None:
        if isinstance(key, (int, float)):
            number = _bounded_float(key, 0.0, 100_000.0, -1.0)
        else:
            normalized = str(key).strip().lower().replace("hz", "")
            for prefix in ("spectral_", "spectrum_", "frequency_", "freq_", "spec_"):
                if normalized.startswith(prefix):
                    normalized = normalized[len(prefix):]
                    break
            normalized = normalized.replace("p", ".").replace("_", "").strip()
            try:
                number = float(normalized)
            except (TypeError, ValueError, OverflowError):
                return None
        return min(cls.FREQUENCIES, key=lambda item: abs(item - number)) if number >= 0 else None

    def set_features(self, features: Mapping[object, object] | Sequence[object]) -> None:
        """Accept named spectral features, 12 bands, or a full 26-feature vector."""

        values = [0.0] * len(self.FREQUENCIES)
        has_value = False
        if isinstance(features, Mapping):
            frequency_index = {frequency: index for index, frequency in enumerate(self.FREQUENCIES)}
            for key, value in features.items():
                frequency = self._frequency_from_key(key)
                if frequency is None:
                    continue
                values[frequency_index[frequency]] = _bounded_float(value)
                has_value = True
        elif not isinstance(features, (str, bytes, bytearray)):
            try:
                source = list(features)
            except TypeError:
                source = []
            if len(source) >= 24:
                source = source[12:24]
            else:
                source = source[:12]
            for index, value in enumerate(source):
                values[index] = _bounded_float(value)
                has_value = True
        self._features = tuple(values) if has_value else ()
        self._draw()

    def set_values(self, values: Mapping[object, object] | Sequence[object]) -> None:
        """Compatibility alias used by the BMI workbench."""

        self.set_features(values)

    def clear(self) -> None:
        self._features = ()
        self._draw()

    @staticmethod
    def _format_energy(value: float) -> str:
        magnitude = abs(value)
        if magnitude >= 1.0e6 or (0 < magnitude < 0.001):
            return f"{value:.2e}"
        if magnitude >= 1000:
            return f"{value:.0f}"
        return f"{value:.3g}"

    def _draw(self) -> None:
        self.delete("all")
        width = max(420, self.winfo_width())
        height = max(200, self.winfo_height())
        left, top, right, bottom = 52.0, 44.0, width - 16.0, height - 45.0
        plot_w, plot_h = max(1.0, right - left), max(1.0, bottom - top)
        maximum = max(self._features, default=0.0)

        self.create_text(16, 15, text="振动频谱能量（12 个固定频带）", fill=COLORS["muted"],
                         anchor="w", font=(UI_FONT, 8, "bold"))
        if maximum > 0:
            dominant = max(range(len(self._features)), key=self._features.__getitem__)
            self.create_text(right, 15,
                             text=f"主频：{self.FREQUENCIES[dominant]:g} Hz  ·  能量 {self._format_energy(maximum)}",
                             fill=COLORS["cyan"], anchor="e", font=(UI_FONT, 8, "bold"))

        for index in range(5):
            fraction = 1.0 - (index / 4.0)
            y = top + (plot_h * index / 4.0)
            self.create_line(left, y, right, y, fill=COLORS["border"], dash=(2, 5))
            label = self._format_energy(maximum * fraction) if maximum > 0 else "0"
            self.create_text(left - 7, y, text=label, fill=COLORS["muted"],
                             anchor="e", font=(NUM_FONT, 6))
        self.create_text(14, (top + bottom) / 2, text="频带能量", fill=COLORS["muted"],
                         anchor="w", font=(UI_FONT, 7))

        slot_w = plot_w / len(self.FREQUENCIES)
        bar_w = max(3.0, slot_w * 0.64)
        dominant = (max(range(len(self._features)), key=self._features.__getitem__)
                    if maximum > 0 else -1)
        for index, frequency in enumerate(self.FREQUENCIES):
            center_x = left + ((index + 0.5) * slot_w)
            x0, x1 = center_x - bar_w / 2, center_x + bar_w / 2
            self.create_rectangle(x0, top, x1, bottom, fill=COLORS["surface_alt"], outline="")
            value = self._features[index] if index < len(self._features) else 0.0
            fraction = value / maximum if maximum > 0 else 0.0
            y0 = bottom - (fraction * plot_h)
            color = COLORS["amber"] if index == dominant else COLORS["cyan"]
            if y0 < bottom:
                self.create_rectangle(x0, y0, x1, bottom, fill=color, outline="")
                self.create_line(x0, y0, x1, y0, fill="#E8FBFF", width=1)
            label = f"{frequency:g}"
            self.create_text(center_x, bottom + 12, text=label, fill=COLORS["text"],
                             anchor="n", font=(NUM_FONT, 6))
        self.create_text((left + right) / 2, height - 8, text="频率 / Hz", fill=COLORS["muted"],
                         anchor="s", font=(UI_FONT, 7))

        if maximum <= 0:
            self.create_text((left + right) / 2, (top + bottom) / 2,
                             text="等待频谱特征数据…", fill=COLORS["muted"],
                             font=(UI_FONT, 9))


class ReasonDonutChart(tk.Canvas):
    """Anomaly-reason share chart with a stable seven-category legend."""

    CATEGORIES: tuple[tuple[str, str, str], ...] = (
        ("unknown", "未知 ID", COLORS["red"]),
        ("timing", "时序异常", COLORS["amber"]),
        ("flood", "总线洪泛", COLORS["purple"]),
        ("dlc", "DLC 改变", COLORS["blue"]),
        ("payload", "Payload 跳变", COLORS["cyan"]),
        ("bus", "总线故障", "#E879F9"),
        ("model_full", "模型已满", "#94A3B8"),
    )

    _ALIASES = {
        "UNKNOWN": "unknown", "UNKNOWN_ID": "unknown", "未知ID": "unknown",
        "未知_ID": "unknown",
        "TIMING": "timing", "PERIOD": "timing", "PERIOD_FAST": "timing",
        "PERIOD_SLOW": "timing", "时序": "timing", "时序异常": "timing",
        "周期异常": "timing",
        "FLOOD": "flood", "GLOBAL_FLOOD": "flood", "洪泛": "flood", "总线洪泛": "flood",
        "洪泛流量": "flood",
        "DLC": "dlc", "DLC_CHANGED": "dlc", "DLC_CHANGE": "dlc", "DLC改变": "dlc",
        "DLC_变化": "dlc", "DLC变化": "dlc",
        "PAYLOAD": "payload", "PAYLOAD_JUMP": "payload", "PAYLOAD跳变": "payload",
        "载荷跳变": "payload",
        "BUS": "bus", "BUS_OFF": "bus", "BUSOFF": "bus", "BUS_ERROR": "bus",
        "总线": "bus", "总线故障": "bus",
        "MODEL_FULL": "model_full", "MODEL": "model_full", "模型满": "model_full",
        "模型已满": "model_full",
    }

    def __init__(self, master: tk.Misc, height: int = 255) -> None:
        super().__init__(master, height=height, background=COLORS["surface"], highlightthickness=0)
        self._counts: dict[str, int] = {key: 0 for key, _label, _color in self.CATEGORIES}
        self.bind("<Configure>", lambda _event: self._draw())

    def set_counts(self, counts: Mapping[str, int]) -> None:
        parsed = {key: 0 for key, _label, _color in self.CATEGORIES}
        if isinstance(counts, Mapping):
            for raw_key, raw_value in counts.items():
                normalized = str(raw_key).strip().upper().replace("-", "_").replace(" ", "_")
                canonical = self._ALIASES.get(normalized)
                if canonical is None:
                    continue
                parsed[canonical] += _bounded_int(raw_value, 0, 2_147_483_647)
        self._counts = parsed
        self._draw()

    def clear(self) -> None:
        self._counts = {key: 0 for key, _label, _color in self.CATEGORIES}
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(420, self.winfo_width())
        height = max(225, self.winfo_height())
        total = sum(self._counts.values())
        center_x = min(width * 0.27, 150.0)
        center_y = height * 0.53
        radius = min(82.0, max(54.0, height * 0.33), center_x - 18.0)
        ring_width = max(13, round(radius * 0.24))
        bbox = (center_x - radius, center_y - radius, center_x + radius, center_y + radius)

        self.create_text(16, 15, text="异常原因分布", fill=COLORS["muted"], anchor="w",
                         font=(UI_FONT, 8, "bold"))
        self.create_arc(*bbox, start=0, extent=359.9, style="arc",
                        outline=COLORS["border"], width=ring_width)
        if total:
            angle = 90.0
            for key, _label, color in self.CATEGORIES:
                count = self._counts[key]
                if count <= 0:
                    continue
                extent = -(count / total * 360.0)
                self.create_arc(*bbox, start=angle, extent=extent, style="arc",
                                outline=color, width=ring_width)
                angle += extent
            self.create_text(center_x, center_y - 7, text=str(total), fill=COLORS["text"],
                             font=(NUM_FONT, 23, "bold"))
            self.create_text(center_x, center_y + 17, text="异常事件", fill=COLORS["muted"],
                             font=(UI_FONT, 8))
        else:
            self.create_text(center_x, center_y - 5, text="0", fill=COLORS["text"],
                             font=(NUM_FONT, 23, "bold"))
            self.create_text(center_x, center_y + 17, text="暂无异常", fill=COLORS["green"],
                             font=(UI_FONT, 8))

        legend_x = max(center_x + radius + 36.0, width * 0.49)
        legend_top = 42.0
        row_height = max(23.0, min(28.0, (height - legend_top - 10.0) / len(self.CATEGORIES)))
        for index, (key, label, color) in enumerate(self.CATEGORIES):
            y = legend_top + (index * row_height)
            count = self._counts[key]
            percent = (count / total * 100.0) if total else 0.0
            self.create_rectangle(legend_x, y - 5, legend_x + 10, y + 5, fill=color, outline="")
            self.create_text(legend_x + 18, y, text=label, fill=COLORS["text"],
                             anchor="w", font=(UI_FONT, 8))
            self.create_text(width - 16, y, text=f"{count}  ·  {percent:.1f}%",
                             fill=color if count else COLORS["muted"], anchor="e",
                             font=(NUM_FONT, 8, "bold"))


def score_tag(score: int) -> str:
    if score >= 700:
        return "critical"
    if score >= 350:
        return "warning"
    return "normal"


def configure_tree_tags(tree: ttk.Treeview) -> None:
    tree.tag_configure("critical", foreground=COLORS["red"])
    tree.tag_configure("warning", foreground=COLORS["amber"])
    tree.tag_configure("normal", foreground=COLORS["green"])
    tree.tag_configure("muted", foreground=COLORS["muted"])


def human_count(value: int) -> str:
    value = int(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)
