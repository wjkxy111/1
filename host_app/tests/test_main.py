from __future__ import annotations

import unittest

from main import configure_tk_scaling


class _FakeTkInterpreter:
    def __init__(self) -> None:
        self.scaling = 0.0

    def call(self, *args: object) -> None:
        if args[:2] == ("tk", "scaling"):
            self.scaling = float(args[2])


class _FakeRoot:
    def __init__(self, dpi: float) -> None:
        self.dpi = dpi
        self.tk = _FakeTkInterpreter()

    def winfo_fpixels(self, value: str) -> float:
        if value != "1i":
            raise ValueError(value)
        return self.dpi


class MainTests(unittest.TestCase):
    def test_tk_scaling_tracks_monitor_dpi_and_is_bounded(self) -> None:
        root = _FakeRoot(144.0)
        self.assertEqual(2.0, configure_tk_scaling(root))
        self.assertEqual(2.0, root.tk.scaling)

        self.assertEqual(1.0, configure_tk_scaling(_FakeRoot(48.0)))
        self.assertEqual(3.0, configure_tk_scaling(_FakeRoot(400.0)))


if __name__ == "__main__":
    unittest.main()
