# 第三方来源与文件边界

本仓库自己的脚本和说明使用根目录的 MIT License。

以下第三方文件没有随本仓库分发，也不受本仓库 MIT License 覆盖：

- NVIDIA 的完整 DTB、IMX219 DTBO、内核模块和 NITO：构建时读取用户本机已安装的 BSP 文件，遵守原许可。本项目没有自行编写或重新发布 IMX219 内核驱动。
- Waveshare 的 `Camera_overrides.tar.gz` / `camera_overrides.isp`：只提供官方下载链接和本机测试结论，不打包该文件。

相机硬件参数参考 [Pi5-IMX219 产品页](https://www.waveshare.com/pi5-imx219.htm)和[对应 Wiki](https://www.waveshare.com/wiki/Pi5-IMX219)。旧 ISP 教程来自 [IMX219-77 Camera Wiki](https://www.waveshare.com/wiki/IMX219-77_Camera)，并非当前 JetPack 上已验证的模组专用标定。

本仓库没有获得 NVIDIA 或 Waveshare 的背书。
