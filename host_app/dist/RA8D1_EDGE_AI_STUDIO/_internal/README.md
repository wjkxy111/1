# RA8D1 Edge AI Studio 统一上位机

这是同时支持 `ra8d1_canfd_edge_ids` 与 `ra8d1_bmi088_vibration_ai` 的 Windows 桌面上位机。它通过 SCI3 自动识别固件并切换工作台：CAN 项目展示总线画像和可解释入侵事件；BMI088 项目展示机器健康、振动/温度趋势、64 点波形、26 维特征和 Top-3 解释。

程序已启用 Windows Per-Monitor V2 高 DPI 原生渲染，并在创建控件前按当前显示器 DPI 同步 Tk 字体比例：在 125%/150% 缩放和高分屏上不会再由系统整窗位图放大，中文、曲线和细线会保持清晰；启动后默认使用当前显示器工作区。

异常检测仍在 RA8D1 上运行，上位机不代替板端推理。因此断开电脑后板端仍能学习和告警，这也是本项目区别于普通 PC 抓包工具的核心。

## 先看效果：无硬件 Demo

已安装 Python 3 时，在本目录双击 `run_host.bat`，或执行：

```powershell
cd C:\Users\34542\Desktop\端侧AI与车辆嵌入式项目\ra8d1_canfd_edge_ids\host_app
python -m pip install -r requirements.txt
python main.py --demo
```

CAN 演示使用与真实固件相同的文本协议，自动经历基线学习、实时监测、未知 ID、洪泛、DLC 变化以及载荷/时序异常。BMI 演示展示一类异常模型的正常基线、振动偏离和温升融合；两者都不需要开发板、摄像头或 USB-CAN-FD 适配器。

```powershell
python main.py --demo can
python main.py --demo bmi
```

自动化界面冒烟检查：

```powershell
python main.py --demo can --smoke-test
python main.py --demo bmi --smoke-test
```

回放随工程提供的原始串口会话：

```powershell
python main.py --replay samples\demo_session.log
python main.py --replay samples\bmi088_demo_session.log
```

## 环境与安装

推荐使用 64 位 Python 3.11～3.13。Tkinter 随 Windows 官方 CPython 安装包提供；运行依赖只有 pySerial。

隔离安装：

```powershell
cd C:\Users\34542\Desktop\端侧AI与车辆嵌入式项目\ra8d1_canfd_edge_ids\host_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

如果 PowerShell 不允许激活脚本，不必修改系统策略，可以直接运行：

```powershell
.\.venv\Scripts\python.exe main.py --demo
```

`run_host.bat` 会优先使用本目录的 `.venv`，找不到时再使用系统 Python，并将附加参数原样传给程序。例如：

```powershell
.\run_host.bat --demo
.\run_host.bat --port COM7 --baud 115200
```

## 连接真实 RA8D1

这里连接的是 **3.3 V TTL USB 转串口模块**，不是 RS-232 电平，也不是 USB-CAN。接线需交叉：

| USB 转串口 | RA8D1 扩展板/核心板 |
|---|---|
| RXD | P409 / TXD3 |
| TXD | P408 / RXD3 |
| GND | GND |
| VCC | **不接** |

串口固定为 `115200-8-N-1`，无硬件流控。操作顺序：

1. 烧录并复位 `ra8d1_canfd_edge_ids` 或 `ra8d1_bmi088_vibration_ai` 固件。
2. 接好 RXD、TXD 和共地，再把 USB 转串口插入电脑。
3. 启动上位机。程序每 2 秒扫描一次串口并优先选择常见 USB-UART（CH340/CH341、CP210x、FTDI、XDS110、J-Link/SEGGER VID 1366），但不会自动占用端口；当前实板已确认 J-Link CDC 为 `COM16`（VID 1366 / PID 1024），核对后点击“连接”。也可用 `python main.py --port COM16 --baud 115200`。
4. 原始控制台应看到 `PROTO,...VERSION,1`；错过启动行时也会按设备专属遥测自动识别。
5. 上位机默认以 2 Hz 发送单字节幂等 `q`。CAN 固件返回 `TELEM/FRAME`，BMI 固件返回 `BMI_TELEM/BMI_WAVE/BMI_EXPLAIN`；不会改变板端学习、校准或监测状态。

不要把 CANH/CANL 接到 USB 转串口。CANH1、CANL1 和总线终端的接线见工程根 README；真实 CAN 总线发送还必须有另一个节点提供 ACK。

BMI088 项目启用扩展板 SDRAM/屏幕时，陀螺仪 CS 必须接 `D3 / P907`，不能再使用与 SDRAM 冲突的 `D9 / PA07`。当前扩展板 LCD 使用 ASCII 5×7 字库，板上显示为清晰英文缩写；完整中文、趋势图、波形、频谱和解释图位于本上位机。

## 已落地功能

- USB 串口热插拔扫描与优先选择、串口连接状态，以及 CAN/BMI088 固件协议自动识别；蓝牙/Modem 虚拟串口会降低优先级，但最终仍由用户点击连接。
- 全中文深色工业界面，中文区域统一采用微软雅黑 UI，并保留协议字段原文以便调试。
- 基线学习/实时监测、自测、回环和 CAN 健康状态展示。
- FPS、估算总线负载、画像数、异常分数、累计帧、异常数、TEC/REC、丢帧及 Bus-Off 指标。
- 异常分数与流量趋势，用于观察攻击前后的变化。
- CAN 系统图谱：动态显示 PC、RA8D1、CAN-FD 收发器及 ECU 总线链路，并联动帧率、画像数、回环、异常分数与 Bus-Off 状态。
- CAN 异常原因环图：按未知 ID、周期、洪泛、DLC、载荷、总线和模型容量七类统计事件占比。
- 最新 CAN/CAN-FD 帧快照表，显示标准/扩展帧、FD/BRS、DLC、Payload、采样次数、分数和原因；相同设备时间戳会去重，不把重复轮询误算成新帧。
- 异常事件、学习画像和原始协议控制台，便于从告警追到原始证据。
- 固件命令快捷控制、手工单字符命令和诊断/画像刷新。
- 无硬件确定性 Demo、全局一键会话录制、CSV 导出和离线回放。
- 串口线程与 Tk 主线程隔离；坏行、未知字段和断连不会直接卡死界面。
- BMI088 机器健康页：窗口、`anomaly_only`/五分类、置信度、温度/温升、推理延迟、基线与健康状态；融合图同时呈现振动、绝对温度和相对温升阈值。
- BMI088 波形与频谱、特征解释、健康事件页面：64 点波形、12 个固定频带能量图、准确映射的 26 维中文特征、Top-3 z² 贡献及健康状态转换。
- 自动区分 `TRAINED` 五分类和 `ONE_CLASS_FALLBACK`；当前默认权重未训练时不会把异常解释伪装成故障五分类结果。

上位机协议的全部字段、兼容规则和原因位定义见 [`../docs/HOST_PROTOCOL.md`](../docs/HOST_PROTOCOL.md)。

## 固件命令

| 命令 | 功能 | 使用提示 |
|---:|---|---|
| `l` | 清空画像并重新学习 | 真实总线应提供完整的正常工况 |
| `m` | 冻结当前模型并进入监测 | 尚无 CAN 帧时固件会拒绝 |
| `s` | 开关离线合成攻击演示 | 无第二个 CAN 节点时优先用它演示 |
| `o` | 开关 CAN 控制器内部回环 | 单板验证发送 API 时使用 |
| `c` | 发送 Classical CAN 测试帧 | Normal 模式需要其他节点 ACK |
| `f` | 发送 CAN-FD+BRS 测试帧 | Normal 模式需要 CAN-FD 节点 ACK |
| `u` | 切换板载显示下一页 | 不影响上位机页面 |
| `i` | 输出诊断、AI 和 CAN 健康信息 | 用于定位 TEC/REC、丢帧、Bus-Off |
| `e` | 输出画像及最近事件 | 仅连接时和手动请求，避免周期性大批量串口输出干扰 CAN 接收 |
| `q` | 输出一次 `TELEM`/`FRAME` 快照 | 幂等；建议 2～5 Hz |
| `h` | 输出串口帮助 | 便于核对固件版本 |

在真实总线上，不要连续点击 `c`/`f`。若没有第二节点提供 ACK，控制器可能累积错误并进入 Bus-Off；单板演示请选择 `s`，或先用 `o` 进入内部回环。

## 录制、导出与回放

录制时，上位机把接收到的完整协议消息写入 UTF-8 JSONL 会话：每条记录保留主机时间、消息种类、解析字段和原始文本。JSONL 适合无损回放和自动化回归，CSV 适合 Excel、Python 或数据分析工具进一步处理。

建议现场演示流程：

1. 连接设备并开始录制。
2. 用正常流量完成学习，进入 Monitoring。
3. 依次注入 Unknown ID、Flood、DLC 和 Payload 异常。
4. 停止录制，导出 CSV，并保留 JSONL 作为可重复的测试证据。
5. 断开硬件后加载会话回放，验证展示和解析不依赖现场总线。

`samples/demo_session.log` 是可直接阅读的原始 UART 协议样例，适合快速验收解析器；界面录制生成的 JSONL 则包含精确主机时间，适合保持会话顺序与节奏。

## 打包成 Windows 应用

打包脚本会创建独立 `.venv-build`，安装运行/测试/打包依赖，先执行测试，再生成 PyInstaller **onedir** 应用：

```powershell
cd C:\Users\34542\Desktop\端侧AI与车辆嵌入式项目\ra8d1_canfd_edge_ids\host_app
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

脚本会先在隔离环境中执行全部测试及 CAN/BMI 两套 Tk 界面冒烟检查，再生成目录版程序和便于拷贝的
`dist\RA8D1_EDGE_AI_STUDIO_Windows_x64.zip`。解压后应保留完整目录，不要只复制单个 EXE。

输出入口：

```text
dist\RA8D1_EDGE_AI_STUDIO\RA8D1_EDGE_AI_STUDIO.exe
```

分发时要复制整个 `dist\RA8D1_EDGE_AI_STUDIO` 目录，不能只复制 EXE。首次构建需要联网下载依赖；之后可复用 `.venv-build`。源码、开源方案评审和第三方声明会随 onedir 目录一起打包。

对外发布前，请按实际 Python/Tcl/Tk、pySerial 和 PyInstaller 版本复核并附带完整许可证；工程记录见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## 自动测试

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
python main.py --demo can --smoke-test
python main.py --demo bmi --smoke-test
```

测试重点包括协议容错、原因位解释、会话保存/回放、CSV 导出和 pySerial `loop://` 收发。真实硬件验收仍需连接 RA8D1，因为自动测试不能覆盖 TTL 电平、交叉接线、MCP2542FD、终端、ACK 和线束质量。

## USB-CAN-FD 与 DBC：下一阶段扩展

当前成品的数据源是 RA8D1 SCI3，展示板端 IDS 的结论；它不伪装成高速通用抓包器。后续可保持现有协议/UI模型，新增：

- `python-can` 数据源：PCAN、Vector、Kvaser 等 USB-CAN-FD 适配器旁路读取原始帧；
- `cantools`：加载 DBC/ARXML，将 Payload 解码成车速、温度等物理信号；
- 双时间线关联：把 USB-CAN-FD 原始帧和 RA8D1 `EVENT` 对齐，量化板端检测延迟；
- ASC/BLF/MF4/SQLite 记录与回归数据集；
- 数据量达到数千帧每秒后，再将 GUI 迁移到 PySide6 + pyqtgraph。

这些依赖没有放进首版 `requirements.txt`，因此“当前可运行”和“未来路线”界限清楚。开源工具的对比、许可证与选择依据见 [`OPEN_SOURCE_REVIEW.md`](OPEN_SOURCE_REVIEW.md)。SavvyCAN 适合在旁边作为通用 CAN-FD 对照工具，但本上位机没有复制 SavvyCAN、BUSMASTER 或其他工程的代码。

## 作为作品集怎么讲

一句话介绍：

> 我在 RA8D1 上实现了可解释的 CAN-FD 在线异常检测，PC 上位机只负责可视化、控制和证据留存；模型学习与推理不依赖电脑。

面试时建议按以下顺序展示：

1. **问题**：固定规则难覆盖未知 ID、异常周期、Flood、DLC 和 Payload 跳变。
2. **端侧方案**：RA8D1 在线学习正常画像，在资源受限环境计算分数与原因位。
3. **工程闭环**：CAN-FD 驱动、ISR 队列、状态机、板载 UI、版本化串口协议、桌面上位机和回放测试形成完整链路。
4. **现场证据**：拔掉 CAN 或不接摄像头也可先用 `s`/Demo 演示；接真实 USB-CAN-FD 后再验证物理层与 ACK。
5. **可靠性意识**：展示 TEC/REC、Drop、Bus-Off、协议容错、线程隔离和自动化测试，而不只展示一张漂亮界面。
6. **诚实边界**：当前是在线统计异常检测而非神经网络，模型保存在 RAM，功能安全和生产部署仍需数据集、持久化、EMC 与系统级验证。

可写入简历的表述：

> 基于 Renesas RA8D1 构建 CAN-FD 端侧入侵检测原型，完成 ID/周期/DLC/Payload/帧率在线画像、可解释告警、SCI3 版本化遥测协议，以及 Python/Tkinter 桌面监控、录制回放和 PyInstaller 交付；通过合成攻击与真实 USB-CAN-FD 流量形成可重复验证闭环。

## 常见问题

- **端口列表为空**：确认 USB 转串口驱动、数据线和设备管理器；蓝牙 COM 口通常不是目标端口。
- **打开端口失败**：关闭串口助手、e² studio 终端或其他占用同一 COM 的程序。
- **全是乱码**：确认 115200-8-N-1、TTL 电平和共地，RX/TX 必须交叉。
- **连接后没有 `TELEM`**：确认烧录的是含 `PROTO`/`q` 的本工程固件，并在原始控制台手工发送 `q`。
- **有状态但没有 `FRAME`**：固件只有在至少接收过一帧后才输出最新帧；可先打开 `s` 自测或接真实 CAN 流量。
- **真实发送后 TEC 上升**：检查第二节点 ACK、500 kbit/s/2 Mbit/s 参数、CANH/CANL、共地和两端终端。
- **Demo 正常、硬件不正常**：说明 GUI/协议链路基本通过，应转查固件版本、串口接线或 CAN 物理层，而不是修改上位机算法。

## 目录

```text
host_app/
├─ main.py                    # 程序入口与命令行参数
├─ ra8d1_can_ids/             # GUI、协议、串口、模型、会话与 Demo
├─ tests/                     # 协议/串口/会话自动测试
├─ samples/demo_session.log   # 原始 UART 回放样例
├─ run_host.bat               # 直接启动
├─ build_exe.ps1              # 隔离环境测试并打包
├─ requirements*.txt          # 运行/开发依赖
├─ OPEN_SOURCE_REVIEW.md      # 开源方案选型记录
└─ THIRD_PARTY_NOTICES.md     # 第三方许可证记录
```
