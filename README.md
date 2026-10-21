# Jetson Orin NX + Waveshare IMX219

实测：Orin NX 16GB，Ubuntu 24.04 / JetPack 7.2.1 / L4T R39.2.1，Pi5-IMX219-77（79.3°），CSI0接入。使用系统 `nv_imx219` 驱动和原有 NITO。

## 偏紫修正

使用带 GStreamer 的系统 OpenCV 和 numpy。**不需要先校准**，`imx219.py` 默认加载我们已经实测的 **white_balance.json**，保存的图像同样经过修正：

```bash
python3 imx219.py
python3 imx219.py --headless --frames 180 --save corrected.jpg
python3 imx219.py --raw-color  # 关闭 LUT，自动白平衡，对照原图
```

| 参数 | 本机第二次白纸标定结果 |
|---|---|
| 白平衡 | `wbmode=2` 白炽灯，脚本选项为 `indoor` |
| 曝光补偿 | `-0.7 EV`，快门/增益仍自动 |
| BGR 增益 | `[0.8691588785, 1, 1.1772151899]` |
| 输入 / 输出 | 1920×1080@30 / BGR 960×540 |

修正采用 ISP 输出后的逐通道 LUT，只在本程序中生效。这是当时室内光照的白点修正，不是厂家通用 ISP；换光源后重新标定。


## 可选：重新标定

放好白纸，ROI 按 960×540 输出填写，避开阴影、反光和边缘：

```bash
python3 imx219.py --wb indoor --ev -0.7 --headless --frames 180 \
  --roi 320 200 440 280 --calibrate-white my-white.json
python3 imx219.py --white-profile my-white.json
```

预热 60 帧，取最后 30 帧通道中位值，以 `G/B、1、G/R` 求 BGR 增益。过曝或太暗时拒绝保存；用白纸另一块区域验证。

## 曝光和增益

```bash
# 固定 20 ms、模拟增益 1.5x、ISP 数字增益 1x
python3 imx219.py --raw-color --shutter-us 20000 --gain 1.5 --isp-gain 1
# 自动曝光，上限 5 ms；模拟增益上限 4x
python3 imx219.py --raw-color --max-exposure-us 5000 --max-gain 4 --isp-gain 1
```

快门参数单位为微秒，传给 Argus 时转成纳秒。以上是用法示例，需按光照和运动调整。[Waveshare 手册](https://www.waveshare.com/wiki/Pi5-IMX219)的 libcamera 参数不能直接照搬到 Jetson。旧 Nano 教程的 `camera_overrides.isp` 在本机出现不兼容字段，因此未采用。

## 没有 /dev/video0 时

`enable_imx219.py` 仅合并本机 IMX219-A 相机 overlay，检查 sensor → NVCSI → VI 链路，不配置其他外设：

```bash
sudo apt install device-tree-compiler v4l-utils
python3 enable_imx219.py
sudo install -m 644 build/imx219-local.dtb /boot/dtb/imx219-local.dtb
sudo cp /boot/extlinux/extlinux.conf /boot/extlinux/extlinux.conf.imx219-backup
```

编辑 extlinux.conf：复制当前启动项，保留 LINUX、INITRD、APPEND，新项设置 `FDT /boot/dtb/imx219-local.dtb`，DEFAULT 指向新项；保留旧项以便回退。已有自定义 FDT/overlay 时先合并原配置，不能直接替换。重启后检查 `v4l2-ctl --list-devices`。

相机单独 DTB 通过离线检查；此前出图在含其他载板设置的 DTB 上验证。源码 MIT；NVIDIA 驱动、DTB/DTBO、NITO 不随仓库分发，沿用 BSP 原许可。
