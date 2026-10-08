"""Entry point for the unified RA8D1 Edge AI Studio."""

from __future__ import annotations

import argparse
import ctypes
import os
import sys


def enable_windows_high_dpi() -> str:
    """Opt into native per-monitor DPI before Tk creates any HWND.

    Without this, Windows may bitmap-scale the complete Tk window, which makes
    Chinese glyphs, Canvas lines and charts visibly soft on 125%/150% displays.
    The fallbacks keep the source runnable on older supported Windows builds.
    """

    if os.name != "nt":
        return "not-windows"
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == (HANDLE)-4.
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
        # A packaged EXE manifest can establish Per-Monitor V2 before Python
        # starts. ERROR_ACCESS_DENIED then means awareness is already fixed.
        if ctypes.get_last_error() == 5:
            return "manifest"
    except (AttributeError, OSError):
        pass
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE == 2 (Windows 8.1+).
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except (AttributeError, OSError):
        return "unaware"


def configure_tk_scaling(root: object) -> float:
    """Synchronize Tk points with the actual monitor DPI after native opt-in.

    Some Tcl/Tk builds retain the legacy 96-DPI scale even when Windows gives
    the process a crisp Per-Monitor-V2 surface.  Querying ``winfo_fpixels``
    keeps Chinese text, hit targets and Canvas annotations physically legible
    without applying any bitmap zoom.
    """

    try:
        dpi = float(root.winfo_fpixels("1i"))  # type: ignore[attr-defined]
        scaling = min(3.0, max(1.0, dpi / 72.0))
        root.tk.call("tk", "scaling", scaling)  # type: ignore[attr-defined]
        return scaling
    except (AttributeError, TypeError, ValueError):
        return 96.0 / 72.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RA8D1 CAN-FD / BMI088 端侧 AI 中文上位机")
    parser.add_argument("--port", help="开发板 SCI3 串口，例如 COM9")
    parser.add_argument("--baud", type=int, default=115200, help="串口波特率（默认 115200）")
    parser.add_argument("--demo", nargs="?", const="can", choices=("can", "bmi"),
                        help="启动无需硬件的确定性演示：can 或 bmi（默认 can）")
    parser.add_argument("--replay", metavar="PATH", help="回放 .jsonl 会话或原始协议 .log")
    parser.add_argument("--smoke-test", action="store_true",
                        help="构造界面并短暂处理事件后退出，用于自动冒烟测试")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    enable_windows_high_dpi()
    # Importing here makes the DPI-before-GUI ordering explicit and robust if
    # the application package later adds modules that create native windows.
    from ra8d1_can_ids.app import create_app

    # ``create_app`` accepts a pre-created root so scaling is fixed before the
    # widget hierarchy and its named fonts are instantiated.
    import tkinter as tk
    root = tk.Tk()
    configure_tk_scaling(root)
    root, app = create_app(root=root, port=args.port, baud=args.baud,
                           demo=args.demo, replay=args.replay)
    if args.smoke_test:
        if not args.demo and not args.replay:
            root.after(20, lambda: app.start_demo("can"))
        # Exercise the selected notebook page as well as object construction.
        # This catches regressions where tab headers exist but no page is active.
        def validate_visible_page() -> None:
            selected = app.notebook.select()
            if not selected:
                raise RuntimeError("冒烟测试失败：上位机没有可见的活动页面")
            page = root.nametowidget(selected)
            if page.winfo_width() <= 1 or page.winfo_height() <= 1:
                raise RuntimeError("冒烟测试失败：活动页面没有完成布局")

        root.after(500, validate_visible_page)
        root.after(850, app.close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
