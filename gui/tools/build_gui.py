# -*- coding: utf-8 -*-
"""
前端构建脚本（开发工具，非应用后端）
--------------------------------------------------------------------------------
输入  : ui/index.html          —— 锁定基准（与《求索下载-UI-v1.0.html》逐字一致，只读）
输出  : index.html             —— 可运行入口
动作  : 仅把末尾的内联演示 <script>…</script> 替换为外置前端逻辑脚本引用
        （frontend/data.js + frontend/app.js），视觉部分（HTML/CSS）不做任何改动。
校验  : 构建后可用 tools/ui_compare.py 对两者截图比对，确认 1:1。
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI_FILE = ROOT / "ui" / "index.html"
OUT_FILE = ROOT / "index.html"

REPLACEMENT = (
    '<script src="frontend/data.js"></script>\n'
    '<script src="frontend/app.js"></script>\n'
    "</body>"
)


def main() -> int:
    if not UI_FILE.exists():
        print(f"[build] 找不到锁定基准: {UI_FILE}", file=sys.stderr)
        return 1

    html = UI_FILE.read_text(encoding="utf-8")

    # 只替换最后一个 </script> 与 </body> 之间的内联脚本块
    new_html, count = re.subn(
        r"<script>[\s\S]*?</script>\s*</body>",
        REPLACEMENT,
        html,
        count=1,
    )
    if count != 1:
        print(f"[build] 预期替换 1 个内联脚本块，实际 {count} 次，已中止（防止误改视觉）", file=sys.stderr)
        return 2

    OUT_FILE.write_text(new_html, encoding="utf-8")
    print(f"[build] 已生成: {OUT_FILE}")
    print(f"[build] 替换内联脚本块: {count} 处；HTML/CSS 视觉部分未改动")
    print(f"[build] 锁定基准保持不变: {UI_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
