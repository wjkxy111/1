# F28P65x + K230 多传感器智能车

这是从现有 MSPM0G3507 小车控制代码中提取算法并迁移到
**LAUNCHXL-F28P65X / TMS320F28P650DK9** 的安全控制底座。F28P65x 负责硬实时
电机、编码器和 8 路灰度循迹；K230 作为视觉/端侧 AI 协处理器，通过 UART
发送车道偏差、曲率、障碍物距离、交通标志和置信度。

## 当前已接通的链路

- ePWM1A/ePWM2A：双路 20 kHz 电机 PWM，方向与使能独立控制。
- eQEP1/eQEP2：双编码器 10 ms 速度快照和闭环反馈。
- 8 路数字灰度：去抖、位置估计、PD 循迹、交叉口和丢线恢复。
- SCIB 115200：K230 字节协议；针对 C28x 16-bit `char` 做了显式 8-bit 屏蔽。
- SCIA 115200：XDS110 虚拟串口安全控制命令。
- 主状态机：上电电机保持失能；只有显式 `g` 且检测到有效轨迹才允许启动。
- 安全停车：`x`/ESC、丢线超时、视觉 STOP、近距离障碍、编码器闭环故障都会
  先撤销桥使能，再清零 PWM。

## 端侧 AI 在哪里

K230 对图像执行车道/标志/障碍物模型推理，只发送结构化结果：

```text
[V1,lane_error_x10_px,curvature_x10000,obstacle_mm,sign,confidence_x1000]
```

例如：

```text
[V1,-123,450,800,3,950]
```

F28P65x 只在帧龄不超过 200 ms 且置信度至少 700‰ 时采用视觉结果；STOP 标志或
300 mm 内障碍物会触发锁存停车。K230 掉线不会破坏本地 8 路循迹，但不会继续
使用过期视觉数据。这种分工比让视觉 Linux/RTOS 直接输出 PWM 更容易验证实时性
和失效安全。

## 安全运行

1. 首次上电不要架在地面上，将驱动轮悬空。
2. 确认电机驱动逻辑输入兼容 3.3 V，电机电源独立供电，并与 LaunchPad 共地。
3. 确认编码器输出、电平转换、每圈计数和左右方向后，再调整 PID。
4. SCIA/XDS110 串口发送单字符 `g` 启动，发送 `x` 或 ESC 立即停车，`r` 清故障。
5. 默认参数只是保守起点，不是针对你车辆辨识后的量产标定值。

详细接线见 [docs/HARDWARE_WIRING.md](docs/HARDWARE_WIRING.md)，成熟度与剩余工作见
[docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)。

## 构建

- CCS：20.3.1
- TI C2000 Compiler：22.6.2.LTS
- C2000Ware：26.01.00.00
- SysConfig：1.28
- 构建配置：`CPU1_LAUNCHXL_FLASH`

在 CCS 中使用 **File → Import Projects** 导入本目录，选择
`CPU1_LAUNCHXL_FLASH` 后 Build。输出文件：

```text
CPU1_LAUNCHXL_FLASH/f28p65x_k230_smart_car.out
```

主机算法测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_host_tests.ps1
```

## 随工程附带的上位机

`host_app/` 包含共用 RA8D1 Edge AI Studio 上位机源码、测试和 Windows 程序。
可直接运行 `host_app/dist/RA8D1_EDGE_AI_STUDIO/RA8D1_EDGE_AI_STUDIO.exe`。
源码运行：先在 `host_app` 下执行 `python -m pip install -r requirements.txt`，
再执行 `run_host.bat`；运行 `run_host.bat --demo can` 或 `run_host.bat --demo bmi`
可查看无需开发板的演示。

这份上位机目前支持 RA8D1 CAN-FD 与 BMI088 协议，尚未适配本智能车的 F28P65x/K230
协议。智能车的实际启停仍按“安全运行”中的 SCIA 串口命令操作。

## 工程文件

- `empty_driverlib_main.c`：安全主状态机和多传感器融合入口。
- `src/platform/`：F28P65x DriverLib 硬件适配。
- `src/control/`：平台无关的编码器、PID、电机和循迹算法。
- `src/communication/`：K230 协议和严格解析器。
- `tests/`：平台无关控制测试。
- `c2000.syscfg`：引脚与外设配置；生成文件不手工修改。
