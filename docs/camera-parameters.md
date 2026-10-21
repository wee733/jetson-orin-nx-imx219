# Waveshare 参数与 Jetson 接口对照

本项目对应 [Waveshare Pi5-IMX219-77 / 79.3° 产品](https://www.waveshare.com/pi5-imx219.htm)和[对应手册](https://www.waveshare.com/wiki/Pi5-IMX219)。厂家页面介绍 8MP IMX219 和镜头选型；本项目模式表来自当前 Jetson 驱动的枚举与实拍，不将厂家树莓派示例的帧率当作 Jetson 保证。

## 驱动到底改了什么

沿用系统已有 `nv_imx219.ko`、本机 NVIDIA IMX219-A 设备树 overlay 和原有 `imx219.nito`。没有自行编写内核驱动，也没有修改传感器寄存器模式表、曝光上限或镜头光学参数。适配解决的是传感器设备树及采集链路缺失。

仅启用相机的构建脚本不会配置串口、USB 或其他载板外设。实际载板型号仍在环境表中保留，便于判断 CSI 接线是否适用。

## 参数含义对齐，接口按 Jetson 使用

| 用途 | Waveshare 树莓派教程 | 本机 Jetson Argus |
|---|---|---|
| 快门时间 | `--shutter`，示例 20000 表示 20 ms | `exposuretimerange="20000000 20000000"`，单位 ns |
| 增益 | `--gain` 可能组合模拟与数字增益 | `gainrange` 是传感器增益，`ispdigitalgainrange` 单独控制 ISP 增益 |
| 曝光补偿 | `--ev` | `exposurecompensation`，本机范围 -2～2 EV |
| 白平衡 | `--awb auto` 等 | `wbmode=1` 自动；2 白炽灯；5 日光 |
| 自动曝光上限 | 取决于 libcamera 调优 | `exposuretimerange` 的上下界 |
| 图像调优文件 | libcamera 的 JSON tuning file | Jetson Argus/NITO；不能直接复制树莓派 JSON |

Waveshare Wiki 某处将 `--shutter` 标作 ms，但其 20000 → 20 ms 示例对应微秒。这里明确使用 `--shutter-us` 表示微秒，传入 Argus 前乘 1000 转成纳秒。

树莓派 `--gain 1.5` 与 Jetson 模拟增益 1.5、ISP 数字增益 1 并不能保证输出完全相同；平台的 ISP、测光、白平衡和增益分配不同。对齐物理含义不等于像素级复现。

## 默认设置

```bash
python3 examples/preview_white_balance.py --wb auto
```

默认自动曝光、自动增益、自动白平衡、0 EV，不额外强制快门或增益范围，也不加载白纸 LUT。输入为原生 1920×1080@30，输出 960×540。

`--wb indoor` 是历史示例名称，实际映射为 Jetson `wbmode=2` 白炽灯预设，并非 libcamera 的 indoor 模式。它只是本次室内实验的选择。

## 20 ms / 1.5x 对照示例

Waveshare 教程给过 20 ms、1.5x 的演示值。Jetson 可用下列命令表达固定曝光、固定模拟增益，并将 ISP 数字增益约束为 1：

```bash
python3 examples/preview_white_balance.py --headless --frames 90 \
  --wb auto --shutter-us 20000 --gain 1.5 --isp-gain 1
```

这是参数用法示例，不是厂家对所有场景的推荐，更不是适合运动目标的统一快门。固定快门与增益后，EV 无法替代曝光调节；亮度不合适时应修改快门、增益或光照。

## 保留自动曝光，限制拖影

```bash
python3 examples/preview_white_balance.py --headless --frames 90 \
  --wb auto --max-exposure-us 5000 --max-gain 4 --isp-gain 1
```

此例允许自动曝光在 13 µs～5 ms、模拟增益 1～4x 范围内工作。5 ms 和 4x 是示例取值；限制后光线不足就会偏暗，需要按真实目标运动、光照和噪声调整。

本机 mode 2 DT 属性 `min_exp_time=13`、`exposure_factor=1000000`，模拟增益范围 `16/16`～`170/16`（1～10.625x）。脚本的 30fps 快门上限取 33000 µs，是示例约束；传感器和 Argus 仍可能按行时间量化实际快门。它不是传感器所有模式的最长曝光。设置值不等于已读取实际曝光元数据。

先用 `gst-inspect-1.0 nvarguscamerasrc` 核对当前 BSP 属性。720p30 的基础采集见 `check_720p30.py`；它保持默认自动曝光，不包含本文的固定快门策略。

## 白纸修正和旧 ISP 文件

白纸 LUT 为可选的应用侧处理，见[白纸修正](white-balance.md)。profile 会记录曝光/增益限制，并在加载时复用；光照变化后应重新验证。

[Waveshare IMX219-77 旧 Jetson Nano 教程](https://www.waveshare.com/wiki/IMX219-77_Camera)提供过 `camera_overrides.isp`。这不证明该文件适用于 Pi5-IMX219-77 + 当前 R39.2.1；本机测试出现不兼容属性，因此未将它设为默认或自动安装。不能将场景 LUT 称作厂家 ISP 标定。
