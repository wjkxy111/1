# RA8D1 Edge AI Studio 上位机开源方案评审

评审日期：2026-08-12

## 1. 结论

首版上位机采用 **Python + Tkinter + pySerial**，代码保持项目专用并使用 MIT 许可证。它通过 SCI3 串口连接 RA8D1，自动承载 CAN IDS 与 BMI088 振动/温度端侧 AI 两个固件的学习、检测、告警和控制结果。首版不强制安装 Qt、CAN 驱动抽象层或 DBC 工具，目标是在普通 Windows 电脑上用最少依赖完成演示和交付。

后续真实总线分析采用双数据源架构：

1. **Board COM 数据源**：通过 pySerial 接收 RA8D1 的 `BOOT`、`MODEL`、`EVENT`、`DIAG`、`AI`、`CAN`、`PROFILE`、`LOG` 等结构化文本，并发送 `l/m/s/o/c/f/u/i/e/h` 控制命令。
2. **USB-CAN-FD 数据源**：可选安装 python-can，从 PCAN、Vector、Kvaser、SLCAN 等适配器接收原始 CAN/CAN-FD 帧；可选安装 cantools，加载 DBC 并解码信号。

这条边界很重要：异常模型和异常分数由 RA8D1 在端侧计算，上位机只负责采集、展示、导出和控制。USB-CAN-FD 数据源用于观察原始总线和交叉验证，不把推理悄悄搬到 PC 上。

## 2. 为什么首版选择 Tkinter + pySerial

- Tkinter 随标准 CPython 提供，不需要额外 GUI 包，Windows 安装 Python 后通常即可运行。
- pySerial 提供 Windows、Linux、macOS 的串口访问和串口枚举，足以承载固件当前的 115200-8-N-1 文本协议。
- 依赖少、启动快，便于在答辩电脑、实验室电脑和面试演示电脑上部署。
- Tkinter 的 `after()` 调度与“后台串口读取 + 主线程刷新控件”模式适合首版的状态卡、事件表、控制按钮和低频趋势图。
- 不提前引入 USB-CAN 驱动、DBC、Qt DLL，可将首版故障范围收敛到串口、协议和界面三层。

首版的边界也写清楚：Tkinter 适合板端 IDS 仪表盘，但不是高吞吐 CAN 帧分析器。若需要数千帧每秒的实时帧表、多轴波形、DBC 浏览器或复杂停靠窗口，应按第 5 节演进，而不是继续堆叠首版界面。

官方资料：

- [Python tkinter 文档](https://docs.python.org/3/library/tkinter.html)
- [pySerial 仓库](https://github.com/pyserial/pyserial)
- [pySerial 文档](https://pyserial.readthedocs.io/)

## 3. 为什么不直接 fork 通用 CAN 工具

### 3.1 SavvyCAN

[SavvyCAN](https://github.com/collin80/SavvyCAN) 是 MIT 许可的跨平台 Qt/C++ CAN 工具。它已有抓包、发送、DBC、绘图、脚本、模糊测试等功能；V220 还加入了 LAWICEL CAN-FD、CAN-FD 数据速率、64 字节显示和 CAN-FD DBC 等改进。

它适合作为**独立对照工具**验证 USB-CAN-FD、DBC 和线上的原始帧，但不作为本上位机的代码基座，原因是：

- 本项目的核心是 RA8D1 自定义 IDS 生命周期，而不是通用 CAN 抓包器。
- 固件输出的是 `EVENT/DIAG/PROFILE/LOG` 等项目协议，SavvyCAN 没有对应的数据模型和页面。
- 为少量专用页面修改大型 C++/Qt 工程，会增加编译、发布和后续维护成本。
- 直接在通用工具内再次实现检测逻辑，容易模糊“推理发生在端侧”这一项目卖点。

### 3.2 BUSMASTER

[BUSMASTER](https://github.com/rbei-etas/busmaster) 使用 GPL-3.0，经典 CAN 仿真、分析和测试能力成熟，但不适合作为本项目基座：

- 其 Windows 驱动接口和构建结构较重，定制 RA8D1 串口协议的成本高。
- [官方硬件支持说明](https://github.com/rbei-etas/busmaster/wiki/Hardware-support) 明确指出，ES582/ES584 的 CAN-FD 功能不包含在开源版本中，需要 CAN-FD add-on。
- GPL 代码并入本上位机会改变整个派生程序的分发义务；本项目不复制 BUSMASTER 源码。

### 3.3 CANgaroo、CANScope 和 CANviz

- [CANgaroo](https://github.com/Schildkroet/CANgaroo) 支持 Windows、CAN-FD、PCAN、Kvaser、Vector、CANable/Candlelight、DBC、实时图和脚本，适合真实总线交叉验证。其 GPL-2.0 代码不复制到本项目。
- [CANScope](https://github.com/dinacaran/CANScope) 是 MIT 许可的 PySide6/pyqtgraph/python-can/cantools 工程，已有 Windows portable 构建、离线帧表、筛选、曲线和导出结构。后续可以参考其分层思想，但首版不需要整仓 fork。
- [CANviz](https://github.com/Chanchaldhiman/CANviz) 是 MIT 许可的浏览器式工具，安装简单并使用 python-can/cantools；其官方路线图仍把完整 CAN-FD UI（FDF/BRS/ESI、64 字节显式支持）列为待完成项，因此不作为当前 CAN-FD IDS 的基础。

## 4. 框架和数据层比较

| 方案 | Windows 与接口 | 实时展示与打包 | 许可证 | 本项目定位 |
|---|---|---|---|---|
| Tkinter + pySerial | Windows 原生 Python GUI；COM 串口 | 首版状态、事件和轻量趋势足够；依赖最小 | Python/PSF；pySerial BSD-3-Clause | **首版采用** |
| python-can + cantools | 多种 USB-CAN 后端、CAN-FD、日志；DBC 解码/编码 | Python API 易于接入现有程序 | LGPL-3.0-only / MIT | 后续可选数据源 |
| PySide6 + pyqtgraph | 成熟的 Windows 桌面组件；可结合 python-can 或 Qt SerialBus | 表格/MVC/线程强，pyqtgraph 适合高频曲线；包体和 Qt DLL 较大 | LGPLv3/GPLv3/商业 / MIT | 第二阶段高性能 GUI |
| Dear PyGui | 跨平台、GPU 加速、内置 ImPlot | 实时曲线强且 MIT；大型工业表格/MVC 生态不如 Qt | MIT | 快速高性能原型备选 |
| Streamlit + Plotly | 本地 Python 服务 + 浏览器 | 仪表盘和离线报告快；密集帧刷新、串口单例生命周期和单 EXE 体验较弱 | Apache-2.0 / MIT | 后续报告页，不作采集主程序 |

参考链接：

- [python-can 仓库](https://github.com/hardbyte/python-can) 与[硬件接口文档](https://python-can.readthedocs.io/en/stable/interfaces.html)
- [python-can SLCAN 文档](https://python-can.readthedocs.io/en/stable/interfaces/slcan.html)：CAN-FD 是非标准扩展的部分支持，当前说明仅列 2 Mbit/s 和 5 Mbit/s 数据速率，不能把所有串口适配器都当作完整 CAN-FD 设备。
- [cantools 仓库](https://github.com/cantools/cantools)
- [Qt for Python](https://doc.qt.io/qtforpython-6/) 与 [Qt 官方 CAN Bus 示例](https://doc.qt.io/qtforpython-6/examples/example_serialbus_can.html)；示例源码标注 BSD-3-Clause，可在保留版权和许可声明的前提下复用连接、FD 位率和帧表设计。
- [pyqtgraph 仓库](https://github.com/pyqtgraph/pyqtgraph)
- [Dear PyGui 仓库](https://github.com/hoffstadt/DearPyGui)
- [Streamlit 仓库](https://github.com/streamlit/streamlit) 与[客户端/服务器架构说明](https://docs.streamlit.io/develop/concepts/architecture/architecture)
- [Plotly.py 仓库](https://github.com/plotly/plotly.py)

## 5. 双数据源演进路线

### 阶段 A：板端串口 IDS Studio（当前首版）

- 安装依赖仅为 pySerial；Tkinter 来自 CPython。
- 自动枚举 COM 口并连接 SCI3 115200-8-N-1。
- 解析板端结构化行，展示学习/监测状态、异常分数、原因、FPS、负载、TEC/REC、丢帧和 Bus-Off。
- 提供固件命令按钮、事件列表、日志保存和无硬件演示入口。
- 数据口径以板端输出为准，保持“RA8D1 端侧推理”的证据链。

### 阶段 B：可选 USB-CAN-FD 旁路采集

- 用户按需单独安装 `python-can`，不写入首版 `requirements.txt`。
- 新增适配器/通道/仲裁速率/数据速率配置；默认使用本固件对应的 500 kbit/s + 2 Mbit/s、ISO CAN-FD。
- USB-CAN-FD 线程只产生原始帧、总线时间戳和适配器状态；Board COM 线程继续产生端侧检测事件。
- 用主机接收时间和 CAN ID 对齐两条流，展示“原始异常帧 → RA8D1 告警”的延迟与对应关系。
- 对 PCAN、Vector、Kvaser 等优先使用厂商驱动后端；SLCAN FD 明确标为实验性。

### 阶段 C：DBC、记录和高性能界面

- 用户按需安装 `cantools`，加载 DBC、显示物理信号和导出解码结果。
- 使用 python-can 的 ASC/BLF/MF4/CSV/SQLite 等记录与回放能力，建立可重复的回归数据集。
- 当 Tkinter 的表格/曲线吞吐成为真实瓶颈时，再迁移到 PySide6 + pyqtgraph；协议解析、领域模型和数据源接口保持独立，避免重写业务逻辑。
- 若复制 Qt 官方示例或 CANScope 的具体代码，必须保留原 BSD-3-Clause/MIT 版权声明；不复制 GPL 工具代码。

## 6. 依赖与分发策略

- `requirements.txt` 只包含 pySerial。Tkinter 不是 pip 包，不应写进依赖文件。
- `requirements-dev.txt` 在运行依赖之上添加测试与 PyInstaller 打包工具。
- python-can、cantools、PySide6、pyqtgraph、Dear PyGui、Streamlit 和 Plotly 均为评审过的可选方案，首版没有将它们作为强制运行依赖。
- 自写上位机代码采用本目录的 MIT License。
- 发布源码或二进制时同时提供 `THIRD_PARTY_NOTICES.md`。若以后打包 Python/Tcl/Tk 运行时、Qt DLL 或 CAN 厂商 SDK，必须按实际打包版本补齐完整许可证、版权声明和可替换动态库要求，不能只依赖本评审摘要。

本文件是工程选型与合规记录，不构成法律意见。实际对外发布前，应以所打包依赖的精确版本及其随附许可证为准复核。
