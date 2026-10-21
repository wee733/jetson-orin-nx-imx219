# Jetson Orin NX + Ubuntu 24.04 + IMX219 实机适配记录

刚刷好系统，插上 IMX219，却没有 `/dev/video0`。这份仓库记录一次从设备树排查、相机出图，到白平衡和 720p30 采集验证的完整过程。

**已验证的组合：Orin NX 16GB + 达妙 DM-ORIN NX V2 + Waveshare Pi5-IMX219-77（79.3°）+ CSI0 + JetPack 7.2.1 / L4T R39.2.1。**

Ubuntu 24.04 这个版本号本身不足以判断兼容性，必须同时核对模块、载板、L4T 和内核。

## 这次到底改了什么

1. 保留系统已有 `nv_imx219` 驱动，使用本机 BSP 自带的单路 IMX219-A overlay，启用 CSI0 的完整传感器、I²C mux、NVCSI、VI 链路。
2. 基于本机原始 DTB 生成新文件，添加独立启动项，保留原启动项和完整备份。
3. 提供真实采集、原尺寸照片、720p30 时序检查和白纸参考修正示例。

没有重新编译内核、替换相机驱动、刷写 QSPI 或修改 MB1 pinmux。此流程使用已刷好系统中的 BSP 文件，不要求建立预刷机 `Linux_for_Tegra` 源码工作区。

## 实机环境

| 项目 | 本次设备 |
|---|---|
| 模块 | Jetson Orin NX 16GB / P3767-0000 |
| 载板 | 达妙 DM-ORIN NX V2 |
| 系统 | Ubuntu 24.04.4 LTS |
| JetPack / L4T | 7.2.1 / R39.2.1 |
| 内核 | 6.8.12-1021-tegra |
| 相机 | Waveshare Pi5-IMX219-77，79.3°，IMX219 |
| 接口 | CSI0，单摄像头 |

其他载板、Orin NX 8GB、CSI1、双摄、其他 L4T 和 Secure Boot 配置没有完成同等实机验证。脚本默认限制为本次验证的平台基线和版本。

## 先判断是不是同一个问题

```bash
head -1 /etc/nv_tegra_release
uname -r
modinfo nv_imx219
v4l2-ctl --list-devices
media-ctl -p
sudo dmesg | grep -Ei 'imx219|nvcsi|capture-vi|i2c.*(fail|error)'
```

本次故障表现是：

- `nv_imx219.ko` 已存在，vermagic 与运行内核匹配。
- 运行中的设备树没有 IMX219 传感器节点。
- `media-ctl -p` 能看到 Tegra 控制器，但没有 sensor → NVCSI → VI 链路。
- 没有 `/dev/video*`，也没有 IMX219 的 I²C probe 记录。

因此这次的第一原因是**没有启用对应的设备树配置**。不能把这个结论套到所有“没有摄像头”的情况：如果已经有 sensor 节点，但日志出现 I²C probe 失败，要继续检查排线、供电、复位、接口和板级接线。

如果已经有 `/dev/video0` 且可正常采集，可以直接跳到验证和应用示例，不需要重复安装设备树。

## 准备工具

已有工具无需重复安装。使用系统提供的 NVIDIA OpenCV，先确认它带 GStreamer 支持。

```bash
sudo apt-get install --no-install-recommends \
  device-tree-compiler v4l-utils gstreamer1.0-tools
python3 -c 'import cv2,numpy; print(cv2.__version__); print(cv2.getBuildInformation())'
python3 scripts/doctor.py --output camera-report.json
```

`doctor.py` 只读。报告默认不收集主机名、MAC、磁盘 UUID 或照片，公开前仍请自行检查。

不要为了解决这个问题直接用 pip 覆盖系统 OpenCV；通用 wheel 可能没有需要的 GStreamer 支持。

## 构建设备树：先只写工作目录

在仓库根目录执行：

```bash
# 仅启用 CSI0 单路 IMX219；build 目录必须尚不存在。
python3 scripts/build_dtb.py --port CSI0 --output build
```

脚本读取本机文件：

```text
/boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv.dtb
/boot/tegra234-p3767-camera-p3768-imx219-A.dtbo
```

它使用 `fdtoverlay` 合并，并检查重复节点、重复 phandle、四个相互对应的图像 endpoint，以及已有无关属性是否被改变。输出包括 `imx219-local.dtb` 和输入/输出校验和清单。

CSI1 提供显式的未验证入口，但不要把能构建等同于能工作：

```bash
python3 scripts/build_dtb.py --port CSI1 --allow-untested-port --output build-csi1
```

## 安装、重启和回退

先预览：

```bash
python3 scripts/install_boot.py --dtb build/imx219-local.dtb
```

检查打印的 diff，确认后应用：

```bash
sudo python3 scripts/install_boot.py --dtb build/imx219-local.dtb --apply
```

脚本会：

- 核对 DTB 与构建清单校验和。
- 将新 DTB 放到单独的、带内容哈希的文件名，不覆盖原始 DTB。
- 备份当前 extlinux 配置至 `/var/backups/jetson-imx219/<时间>/`。
- 从当前 DEFAULT 启动项复制内核、initrd 和 APPEND，新增启动项并设为默认。
- 保留原启动项；**没有配置自动启动失败回退**。

本脚本不自动重启。选择合适时间手动执行 `sudo reboot`。

如果当前启动项已有其他 overlay，脚本会拒绝自动组合，需人工核对。已有自定义 FDT 时，应用操作也会拒绝直接覆盖；只有确认新 DTB 已保留所需板级配置后才使用 `--allow-replace-fdt`。不要为了绕过检查盲目加参数。

回退时使用安装脚本实际打印的备份目录：

```bash
sudo python3 scripts/rollback_boot.py --backup /var/backups/jetson-imx219/<时间>
sudo python3 scripts/rollback_boot.py --backup /var/backups/jetson-imx219/<时间> --apply
```

回退脚本会核对备份，并拒绝覆盖安装后又被编辑的启动配置。若新配置无法进入系统，需要从启动菜单选择保留的原启动项，或通过你的恢复通道修复 extlinux；不能依靠运行中的回退脚本自救。

## 重启后验收

```bash
ls -l /dev/video*
v4l2-ctl --list-devices
media-ctl -p
sudo dmesg | grep imx219
```

本次成功后出现 `imx219 9-0010`、`/dev/video0`，以及完整的 sensor → NVCSI → VI 图像链路。I²C 总线编号可能因配置变化，不能单凭“不是 9-0010”判断失败。

真实 RAW 采集测试：

```bash
timeout 20 v4l2-ctl -d /dev/video0 \
  --set-fmt-video=width=1920,height=1080,pixelformat=RG10 \
  --set-ctrl=sensor_mode=2 --stream-mmap --stream-count=60 --stream-to=/dev/null
```

Argus → OpenCV：

```bash
# 示例输入是原生 1920×1080；预览输出缩小为 960×540。
python3 examples/preview_white_balance.py --headless --frames 90 --wb auto
python3 examples/check_720p30.py --output capture-timing.json
```

第二个脚本验证的是**采集与 BGR 转换**，不包括你的检测算法或传感器到结果的完整延迟。

## 分辨率与视野

本机驱动枚举并实际采集过以下模式：

| sensor-mode | 分辨率 | 模式最高帧率 |
|---:|---|---:|
| 0 | 3280×2464 | 21 fps |
| 1 | 3280×1848 | 28 fps |
| 2 | 1920×1080 | 30 fps |
| 3 | 1640×1232 | 30 fps |
| 4 | 1280×720 | 60 fps |

**原生 1080p 是裁剪读出，视野会比全幅模式小。** 不要把“输出分辨率较大”当成“视野较大”。本次不同模式照片也确认了这个现象。3280×1848 可以再缩小到 1920×1080，但该采集模式最高 28 fps。

拍摄每种模式的原尺寸照片：

```bash
python3 examples/capture_all_modes.py --output captures
```

模式表是这套驱动的结果，不是 IMX219 传感器所有可能工作模式的穷举。

## 720p30 的算法输入

固定输入 1280×720 时，可以直接使用 `sensor-mode=4` 并请求 30 fps：

```text
nvarguscamerasrc sensor-id=0 sensor-mode=4
! video/x-raw(memory:NVMM),width=1280,height=720,format=NV12,framerate=30/1
! nvvidconv
! video/x-raw,width=1280,height=720,format=BGRx
! videoconvert
! video/x-raw,format=BGR
! appsink max-buffers=1 drop=true sync=false
```

这里使用 Argus/ISP、默认 VIC 格式转换和 CPU BGRx→BGR 转换，**没有使用 NVENC**。NVENC 用于压缩编码录像或推流，不是二维码解码器。

缓存一帧有助于避免积压旧图像，但算法处理超过 33.3 ms 时仍可能掉帧，不能以此保证每帧都完成检测。采集、算法、显示/录像和通信应分开计时。

## 曝光、增益和 Waveshare 参数

参见 [参数对照与曝光示例](docs/camera-parameters.md)。默认自动曝光、自动白平衡和 0 EV；固定快门、增益和白纸修正都需显式选择。厂家树莓派命令与 Jetson Argus 接口不同，不能原样照搬。

## 偏紫、白平衡与旧版 ISP

这次测试过 Waveshare IMX219 系列公开的旧 `camera_overrides.isp`。在这套 R39.2.1 系统中出现多个 `Invalid isp config attribute`，画面没有明显改善，因此已撤回。结论限于**这个下载文件和这套系统**，不代表所有文本 ISP 配置都不能用。

本机原来的 `imx219.nito` 保持不变。本次室内实验使用固定白平衡预设加应用侧逐通道 LUT，按当前光照下的白纸重新求取增益；公开示例默认仍为自动白平衡。它是白点中性修正，不是完整 ISP、镜头阴影或色卡标定；不会自动修好其他应用的画面。

[白纸修正步骤](docs/white-balance.md)包含曝光、ROI 选择和独立区域验证方法。仓库没有发布本机光照下的增益作为通用标定，也没有打包私人照片。

## 本次证据与复现边界

[实测记录](docs/validation.md)和 [脱敏数值结果](results/validated-session.json)保留了实机环境、采集结果、帧间隔抖动及白纸修正范围。

离线测试：

```bash
python3 -m unittest discover -s tests -v
```

本仓库是一次实机适配经验，不是所有 Jetson、载板和 IMX219 模组的通用兼容保证。不要把短时出图测试当作无人机飞行验证。

## 上传到 GitHub

参见 [发布步骤](docs/publishing.md)，包含仓库描述、topics 和上传前检查。

## 来源和许可

本仓库自己的代码和文档使用 [MIT License](LICENSE)。第三方文件不随仓库分发，详情见 [来源与许可边界](THIRD_PARTY_NOTICES.md)。

- [Waveshare Pi5-IMX219 产品](https://www.waveshare.com/pi5-imx219.htm)
- [Waveshare Pi5-IMX219 Wiki](https://www.waveshare.com/wiki/Pi5-IMX219)
- [Waveshare IMX219-77 的旧 Jetson ISP 教程](https://www.waveshare.com/wiki/IMX219-77_Camera)
- [NVIDIA R39.2.1 相机支持表](https://docs.nvidia.com/jetson/archives/r39.2.1/DeveloperGuide/SD/CameraDevelopment/CameraDevelopmentSupportMatrix.html)
- [NVIDIA R39.2.1 GStreamer 文档](https://docs.nvidia.com/jetson/archives/r39.2.1/DeveloperGuide/SD/Multimedia/AcceleratedGstreamer.html)
