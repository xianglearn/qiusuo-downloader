# 求索下载

基于 [DingTalkDownloader](https://github.com/ULing19/DingTalkDownloader) 改造的多平台下载器。

- **钉钉**：保留全部原功能（单个直播 / 群批量采集 / 闪记 / 群文件）
- **其他平台**：B站、抖音、慕课等 90+ 平台（经 MediaGo）
- **两条路线架构**：钉钉专用链路 + 通用平台链路，互不干扰

## 文档导航

- **策划方案.md** —— 完整实现依据（新对话据此实现）
- **技术组件清单.md** —— 三引擎 + Python 依赖 + 部署要求
- **src/** —— 上游源码（改造起点，11 个 py）

## 快速开始（从源码）

```bash
cd src
python -m pip install -r requirements-gui.txt
python gui_downloader.py
```

需要与主程序同目录的三个引擎：`GoDingtalk.exe`、`mediago.exe`、`ffmpeg.exe`。

## 合规声明

本工具仅供下载本人有权访问的内容，遵守各平台服务条款与版权法规，严禁盗版传播。登录会话（cookies.json）严禁公开。
