# 求索下载 GUI 前端（DV1.0）

纯前端桌面工具界面，基于《求索下载-UI-v1.0.html》1:1 像素复刻。**不包含后端**：
所有业务逻辑以「前端数据层」方式在浏览器内模拟，数据一律以 JSON 快照 + 事件推送的方式流入界面。

## 一、目录结构与职责边界

```
GUI前端\
├── index.html              # 可运行入口（由 ui/index.html 构建生成，视觉逐字节一致）
├── ui\
│   └── index.html          # ★ 锁定基准：与《求索下载-UI-v1.0.html》逐字一致，只读，不改
├── frontend\
│   ├── data.js             # 数据层（模拟业务）：任务/配置/日志/下载引擎，无 DOM，纯 JSON 快照+事件总线
│   └── app.js              # 控制器（UI 逻辑）：DOM 渲染与交互绑定，只消费 data.js 的 JSON
├── tools\
│   ├── build_gui.py        # 构建脚本：由锁定基准生成 index.html（仅替换内联演示脚本为外置脚本）
│   ├── ui_compare.py       # 界面截图比对校验（Edge 无头渲染 + 像素差分）
│   └── smoke_test.js       # 数据层冒烟测试（Node 直接运行，无需浏览器）
└── docs\screenshot-diff\   # 校验产物：baseline/candidate/diff.png + report.txt
```

职责边界（三层隔离，只允许单向依赖）：

| 层 | 文件 | 职责 | 禁止 |
|---|---|---|---|
| 视觉层（锁定） | `ui/index.html` | 界面结构与样式，1:1 像素规范 | 任何写入/改动 |
| 数据层 | `frontend/data.js` | 业务状态唯一来源；对外只给 JSON 快照、只发 JSON 事件 | 引用 DOM、修改界面 |
| 控制器 | `frontend/app.js` | 渲染与交互；从 data.js 取 JSON 渲染进锁定 DOM | 持有业务状态、硬编码数据 |

## 二、运行方式

无需安装任何依赖，双击 `index.html` 即可用系统浏览器打开（Chrome / Edge 均可）。

- 左侧：粘贴链接 →「解析到任务列表」；「导入文本 / 二维码 / 清空 / 批量采集 / 一键批量采集」均可用
- 右侧：任务表支持筛选（全部/下载中/已完成/失败）、全选、行内「打开 / 删除」
- 底部：「开始下载」驱动数据层模拟引擎（进度/速度/日志/总进度实时推进），「停止」暂停；「重新登录 / 检查更新 / 设置」均有交互
- 右上角：主题切换（深/浅色）
- **窗口缩放（客户端基础交互）**：四边 + 四角均可拖动调整——拖哪条边/角，窗口就朝哪个方向伸缩；内容为**流体布局**，随窗口尺寸自动重排铺满（左栏增高、表格铺满、底部栏贴底），不会出现“边框拉大、内容留空”的分离

## 三、重新构建 / 校验 / 测试

```bash
# 1. 重新生成 index.html（如后续改了锁定基准，需重跑；视觉部分不会被动）
python tools\build_gui.py

# 2. 界面截图比对校验（交付前必跑；默认冻结动画消除时序假差异）
python tools\ui_compare.py --window 1040,800 --min-similar 0.995

# 3. 数据层冒烟测试（无需浏览器）
node tools\smoke_test.js
```

校验判据：像素一致率 ≥ 99.5%（当前实测 **100%**，见 `docs/screenshot-diff/report.txt`）。

## 四、后续接入真实后端（预留说明）

数据层 `data.js` 是唯一业务出口，且不依赖 DOM。需要接入真实下载/钉钉接口时，
只需在 `data.js` 内部把模拟逻辑替换为 `fetch` 调用（本地服务、PyWebView 桥或任意 HTTP JSON 接口均可），
保持 `snapshot / parseLinks / startAll / stopAll / on` 等对外 API 签名不变，界面层零改动。

## 五、校验记录

- `docs/screenshot-diff/baseline.png`  —— 锁定原版截图（Edge 无头，动画冻结）
- `docs/screenshot-diff/candidate.png` —— 交付前端截图（同一渲染条件）
- `docs/screenshot-diff/diff.png`      —— 差异高亮图（红 = 差异像素，当前为空）
- `docs/screenshot-diff/report.txt`    —— 比对报告（像素一致率 100%，PASS）
