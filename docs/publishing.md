# 上传 GitHub

本目录已经可以作为独立仓库使用。先阅读根目录 MIT License；若你希望更换项目名、作者署名或自有代码许可证，可以在第一次发布前调整。第三方文件的许可不会随之改变。

在 GitHub 创建一个空仓库，然后在本目录执行：

```bash
git init -b main  # 本机目录已初始化；解压 ZIP 后需要执行
git add .
git diff --cached --stat
git commit -m "Document and reproduce IMX219 bring-up on Jetson Orin NX"
git remote add origin <你的GitHub仓库地址>
git push -u origin main
```

如果本地 Git 尚未设置提交身份，按你的 GitHub 身份设置后再提交；不要照抄别人的姓名或邮箱。

建议仓库描述：

> Jetson Orin NX + Ubuntu 24.04 / JetPack 7.2.1 + IMX219 实机适配记录，包含 IMX219 相机设备树适配、曝光/增益设置、采集验证、白平衡示例和回退流程。

建议 topics：`jetson`、`orin-nx`、`imx219`、`ubuntu-24-04`、`jetpack`、`camera`、`device-tree`。

上传前检查：

- 不添加 `build*`、captures、local、日志、启动配置备份或整套 vendor 下载。
- 不添加实验室照片、磁盘 UUID、MAC、主机名、密钥或私人路径。
- 未来接受其他板型的贡献时，记录具体硬件和 L4T，不把 Ubuntu 版本当兼容性证明。
- Issue 中附简要环境、相关 camera 日志和 media graph；公开前先脱敏。

项目公开仓库：https://github.com/wee733/jetson-orin-nx-imx219 。上述流程也可用于发布你自己的派生项目。
