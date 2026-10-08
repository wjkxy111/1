# 硬件接线表

以下映射对应 `c2000.syscfg`，目标板为 LAUNCHXL-F28P65X。

| 功能 | F28P65x 管脚 | 接口/说明 |
|---|---:|---|
| 左电机 PWM | GPIO0 / ePWM1A | J8 BP78 |
| 左电机方向 | GPIO1 | J8 BP77 |
| 右电机 PWM | GPIO2 / ePWM2A | J8 BP80 |
| 右电机方向 | GPIO3 | J8 BP79 |
| 左驱动使能 | GPIO6 | J4 BP38，默认低 |
| 右驱动使能 | GPIO7 | J4 BP37，默认低 |
| 左编码器 A/B | GPIO20/GPIO21 | J12 pin 1/2 |
| 右编码器 A/B | GPIO24/GPIO79 | J13 pin 1/2 |
| 灰度 0..7 | GPIO8,9,10,11,14,15,16,17 | 从左到右，默认按低有效读取 |
| K230 TX/RX | GPIO38/GPIO55 | SCIB，115200 8-N-1 |
| 调试 TX/RX | GPIO42/GPIO43 | SCIA，经 XDS110 虚拟串口 |

## 必须确认的电气条件

- LaunchPad GPIO 不是 5 V 容忍输出；外部模块的高电平不得超过器件允许值。
- J12/J13 的板载电平转换需要按官方跳线设置路由；只有 A/B 的编码器应将 Index
  留空，不要悬空接入别的信号。
- 电机不能使用 LaunchPad 5 V 直接供电，驱动器与控制板必须共地。
- 若驱动器是 TB6612 类双方向输入，而不是 PWM+DIR+EN，需要重新分配第二方向脚，
  不能直接套用当前 HAL。
- 首次调试必须让轮胎离地，并先验证 `x`/ESC 能立刻撤销两路 EN。

## K230 串口

交叉连接：F28 GPIO38/SCIB-TX → K230 RX，F28 GPIO55/SCIB-RX ← K230 TX，GND 共地。
两侧均使用 3.3 V TTL，不连接 USB 转串口模块的 VCC。

