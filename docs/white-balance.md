# 白纸参考修正：能解决什么，不能解决什么

这次默认自动白平衡下画面偏紫。固定 `wbmode=2`（白炽灯预设）减轻了紫色，但白纸仍可能偏蓝，因此又增加了应用侧的逐通道修正。

脚本处理的是 ISP 输出的 8-bit BGR。它按白纸参考点求三个通道的比例，用 LUT 作用于新采集的每一帧。没有编辑 NVIDIA NITO，也没有重新标定传感器的光谱响应或镜头阴影。

## 1. 固定场景和拍摄配置

```bash
python3 examples/preview_white_balance.py --wb indoor
```

本示例的输入固定为 IMX219 mode 2 / 1920×1080@30，输出为 960×540。原生 1080p 有裁剪；这个程序不是全视野示例。按 Q 或 Esc 退出。

把白纸放在待使用的光照中，避免反光、阴影分界、彩色灯照射和过近失焦。不要把白纸当作标准色卡：普通纸可能带有荧光增白剂，混合光源也会让同一张纸的不同位置呈不同颜色。

## 2. 选择白纸内部的 ROI

ROI 坐标对应 **960×540 输出**，格式是 `x0 y0 x1 y1`。以下数字仅演示用法，必须改成你的白纸位置。

```bash
mkdir -p local
python3 examples/preview_white_balance.py \
  --wb indoor --headless --frames 180 --ev -0.7 \
  --roi 320 200 440 280 \
  --calibrate-white local/white-profile.json \
  --save local/before.jpg
```

- 前 60 帧用于收敛，最后 30 个白纸采样的通道中位数用于求增益。
- 若太暗、接近饱和或采样区域出现较多裁切像素，脚本拒绝保存。
- `--ev -0.7` 只是本次实验用的曝光补偿值，不是所有场景的推荐默认值。根据你的白纸亮度调整。
- 曝光补偿会写入 profile；以后加载该 profile 时自动采用对应值。
- ROI 要避开边缘、图案、手、线缆和阴影。不要为了让数值相等而把 ROI 选在错误物体上。

## 3. 应用到下一次真实采集

```bash
python3 examples/preview_white_balance.py \
  --wb indoor --white-profile local/white-profile.json
```

或保存验证图片：

```bash
python3 examples/preview_white_balance.py \
  --wb indoor --headless --frames 180 \
  --white-profile local/white-profile.json --save local/after.jpg
```

必须再检查白纸上另一块未参与拟合的区域。通道接近只能说明该白点更中性，不能说明所有颜色都准确。

## 适用范围

- 更换光源、位置、镜头、相机模式或 ISP 配置后，需要重新验证。
- 这个 LUT 在示例程序中生效；其他进程直接读取相机不会自动获得相同修正。
- 用于神经网络时，颜色处理应和训练时一致。加入 LUT 前应比较真实算法效果。
- 本次约 1 ms/帧的开销是在 960×540 输出上测得，不能直接套到 8MP 或其他负载。
- 没有证明这套室内修正适合无人机的所有室外光照。

## 旧 Waveshare ISP 文件的实测

来源：<https://files.waveshare.com/upload/e/eb/Camera_overrides.tar.gz>

本次解出的 `camera_overrides.isp` SHA-256：

```text
c6b8cafffa5f218a85f73d323e2a72b382194b84b39ff9a7804fffc1819638ec
```

文件中有 2019 年的生成标记。本机 Argus 在读取它时，对多个字段输出 `Invalid isp config attribute`，随后仍报告使用 `imx219.nito`。连续采集成功，但画面没有明显改善，因此撤回该文件并重启 Argus 恢复原配置。

不要把给树莓派 libcamera 的 JSON 配置直接安装到 Jetson，也不要把别的模组的 ISP 文件当成当前模组的已验证标定。本仓库不提供自动下载或安装旧 ISP 的脚本。
