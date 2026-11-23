# Jetson Orin NX + Waveshare IMX219-77（79.3°）

[English](README.md) | **简体中文**

适用 CSI0、P3768/P3767-0000、Ubuntu 24.04。设备树工具识别 L4T R39.2.1 和 R39.2.2，不代表任意载板均已验证。此前在 R39.2.1 上出图；已在 R39.2.2 上验证 CONFIG override 加载和采集。

## 先在 Argus ISP 中校正镜头，再转换 RGB 或送给 NVENC

RBP194 使用树莓派 V2 镜头的阴影校正表，套在不同光学系统上会放大边缘红光。不要整份安装旧 Nano 标定：ISP4 的部分键在 Orin 上不受支持，且缺少 v4 AWB 映射。R39.2.1 之前的机载设置使用 NITO；选中 NITO 或保留旧的 nvcam 缓存都可能使文本配置不起作用。磁盘上存在 `imx219.nito` **不等于**它正被使用。

在 Jetson 上使用此镜头实际的 Waveshare 校准文件，默认路径 `/home/nvidia/workspaces/damiao-bringup/waveshare-isp/camera_overrides.isp`。脚本从本机 `libnvodm_imager.so` 提取 RBP194，仅导入两者共有的光学键，保留三套完整网格，并将灰线和色温映射同步给 v4。先生成到**不存在**的文件，无需 sudo：

```bash
python3 install_isp_override.py --output build/camera_overrides.isp
```

文件不在默认位置时，用 `--waveshare 路径` 指定。确认飞行器落地未解锁，退出所有相机客户端，以 CONFIG 模式安装。这是**整台主机**的 override，多相机系统需验证所有受影响设备。

```bash
sudo python3 -I install_isp_override.py --install
```

脚本保存旧文件或「原先无文件」状态，安装为 root:root 0644，清除 nvcam 与 serial 两类缓存，重启 Argus，采集 60 帧，检查**本次服务实例**有 `Found override file` 且无 `Invalid isp config attribute`。验证失败会回退；脚本不删除 NITO，也不修改服务的环境变量。卸载并恢复（同样会重启 Argus）：

```bash
sudo python3 -I install_isp_override.py --uninstall
```

## 实拍和验收

需要带 GStreamer 的系统 OpenCV 和 NumPy。CLI 和 `IMX219()` 默认使用原生 ISP 色彩：自动白平衡（`wbmode=1`）、0 EV、不加载 8-bit LUT。`--raw-color` 与默认行为相同，并非输出 Bayer。此工具给出 960×540 BGR；机载 ROS app 的原图是 1280×720 RGB8。

```bash
python3 imx219.py --headless --frames 180 --max-exposure-us 5000 --save frame.png
```

建议先试 5000–8000 µs **上限**。它与固定快门 `--shutter-us` 互斥；AE 可以缩短快门、自动调整增益。较短上限不能增加进光量：暗处仍会有彩噪。请在已知照明下用中性灰/白板检查中心与四角，再用运动边缘检查拖影。日志没有非法属性，不代表画质已验收。

仅针对特定光源需要微调时，放置不反光的白纸，按输出坐标选择 ROI：

```bash
python3 imx219.py --headless --frames 180 --max-exposure-us 5000 --roi 320 200 440 280 --calibrate-white my-white.json
python3 imx219.py --white-profile my-white.json
```

旧的白炽灯、−0.7 EV 配置仅在显式使用 `--white-profile white_balance.json` 或 `IMX219('white_balance.json')` 时启用。应用层 LUT 不影响其他 Argus 客户端。

## 仅在相机设备缺失时处理设备树

`enable_imx219.py` 使用 `device-tree-compiler` 包的 `fdtoverlay` 在新目录生成文件，不写 `/boot`。先按命令行顺序合并所有额外载板 overlay，再合并 IMX219-A。达妙的 USB overlay 引用 `dm_usb*` 符号，必须配合含这些符号的基底；直接用 stock DTB 会报 `FDT_ERR_NOTFOUND`，不能为绕过错误而丢掉载板 overlay。

```bash
python3 enable_imx219.py --base /home/nvidia/workspaces/damiao-bringup/local-base.dtb --extra-overlays /home/nvidia/workspaces/damiao-bringup/damiao-v2-uart-usb3.dtbo --output build-dt-new
```

标准参考载板可省略 `--extra-overlays`，但基底仍须匹配。`manifest.json` 记录实际输入顺序、SHA256、相机图链验证和输出摘要。离线验证不等于 UART/USB 通电测试。若另行安装 DTB，保留原启动项以便恢复；本次 ISP 修复不需要刷写 DTB 或重启整机。

源码 MIT；NVIDIA 驱动、DT/DTBO、NITO 和 ISP 表不随库分发，在本机按各自许可生成。
