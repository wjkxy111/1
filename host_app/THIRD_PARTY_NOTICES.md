# Third-Party Notices

This file records the third-party software used by, or evaluated for future use in, the RA8D1 Edge AI Studio host application. The project's original host-application code is licensed under the MIT License in `LICENSE`.

## Components required by the first release

### Python / Tkinter

- Project: CPython and the `tkinter` standard-library module
- Homepage: https://www.python.org/
- Source: https://github.com/python/cpython
- License: Python Software Foundation License Version 2 and other notices shipped with the selected CPython distribution
- License text: https://docs.python.org/3/license.html

Tkinter is part of the standard CPython distribution; it is not installed from `requirements.txt`. Tkinter calls the separately versioned Tcl/Tk libraries bundled with or installed for Python. A packaged executable that redistributes Python, Tcl, or Tk must include the exact license files and notices shipped with the redistributed runtime version.

### pySerial

- Project: pySerial
- Homepage: https://pyserial.readthedocs.io/
- Source: https://github.com/pyserial/pyserial
- License: BSD-3-Clause
- Copyright: Copyright (c) 2001-2020 Chris Liechti
- License text: https://github.com/pyserial/pyserial/blob/master/LICENSE.txt

The pySerial license notice is reproduced below:

> Copyright (c) 2001-2020 Chris Liechti <cliechti@gmx.net>
>
> All Rights Reserved.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are met:
>
> * Redistributions of source code must retain the above copyright notice,
>   this list of conditions and the following disclaimer.
> * Redistributions in binary form must reproduce the above copyright notice,
>   this list of conditions and the following disclaimer in the documentation
>   and/or other materials provided with the distribution.
> * Neither the name of the copyright holder nor the names of its contributors
>   may be used to endorse or promote products derived from this software
>   without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
> AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
> IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
> ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
> LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
> CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
> SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
> INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
> CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
> ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
> POSSIBILITY OF SUCH DAMAGE.

## Development-only component

### pytest

- Project: pytest
- Homepage: https://pytest.org/
- Source: https://github.com/pytest-dev/pytest
- License: MIT
- License text: https://github.com/pytest-dev/pytest/blob/main/LICENSE

pytest is listed only in `requirements-dev.txt` and is not required to run the host application.

### PyInstaller

- Project: PyInstaller
- Homepage: https://pyinstaller.org/
- Source: https://github.com/pyinstaller/pyinstaller
- License: GPL-2.0-or-later with a special exception for distributing bundled applications
- License text: https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt

PyInstaller is listed only in `requirements-dev.txt` and is used by `build_exe.ps1`. Its bootloader exception allows the generated application to retain this project's license, but does not remove the license obligations of Python, Tcl/Tk, pySerial, or any other packaged component.

## Evaluated optional components not required by the first release

The following packages and applications are not installed by `requirements.txt` and are not necessarily distributed with this project. They are recorded here so that a future USB-CAN-FD, DBC, plotting, or packaging release performs an explicit license review before enabling them.

| Component | Intended optional use | License | Official source |
|---|---|---|---|
| python-can | USB-CAN/CAN-FD abstraction, logging and replay | LGPL-3.0-only | https://github.com/hardbyte/python-can |
| cantools | DBC/ARXML parsing, signal encode/decode | MIT | https://github.com/cantools/cantools |
| PySide6 / Qt for Python | Future high-performance native GUI | LGPLv3, GPLv3, or commercial | https://doc.qt.io/qtforpython-6/ |
| pyqtgraph | Future real-time plots for a Qt GUI | MIT | https://github.com/pyqtgraph/pyqtgraph |
| Dear PyGui | Alternative GPU-accelerated GUI | MIT | https://github.com/hoffstadt/DearPyGui |
| Streamlit | Optional browser-based report/dashboard | Apache-2.0 | https://github.com/streamlit/streamlit |
| Plotly.py | Optional interactive report charts | MIT | https://github.com/plotly/plotly.py |
| SavvyCAN | Standalone CAN/CAN-FD comparison and validation tool | MIT | https://github.com/collin80/SavvyCAN |
| CANScope | Architectural reference for offline trace/plot UI | MIT | https://github.com/dinacaran/CANScope |
| CANgaroo | Standalone CAN-FD comparison tool; no code copied | GPL-2.0 | https://github.com/Schildkroet/CANgaroo |
| BUSMASTER | Evaluated and rejected as a code base; no code copied | GPL-3.0 | https://github.com/rbei-etas/busmaster |

The [Qt for Python CAN Bus example](https://doc.qt.io/qtforpython-6/examples/example_serialbus_can.html) is marked `BSD-3-Clause` in its source headers. If a future version copies or adapts that example, its copyright headers and BSD notice must remain with the derived files.

## Distribution checklist

Before releasing a packaged executable:

1. Generate an inventory from the exact locked environment and packaged files.
2. Replace summaries with the complete license and copyright notices shipped by those exact versions.
3. Include the selected Python/Tcl/Tk runtime notices if the runtime is bundled.
4. If PySide6/Qt is introduced, satisfy the applicable LGPLv3 or commercial-license terms and keep Qt libraries replaceable as required by the chosen distribution model.
5. Include vendor SDK/driver notices for any packaged PCAN, Vector, Kvaser or other adapter binaries; their terms are separate from python-can.
6. Do not copy code from GPL tools into the MIT host application without deliberately accepting and documenting the resulting GPL obligations.

This notice is an engineering compliance record and is not legal advice.
