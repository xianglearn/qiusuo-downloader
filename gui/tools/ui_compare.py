# -*- coding: utf-8 -*-
"""
界面截图比对校验工具（交付前验证：视觉 1:1）
--------------------------------------------------------------------------------
用法  : python tools/ui_compare.py [--window 1040,800] [--tolerance 2] [--min-similar 0.995]
输入  : ui/index.html（锁定基准，含内联演示） vs index.html（交付入口，前端逻辑驱动）
流程  :
  1. 用本机 Edge 无头渲染两个页面为 PNG（同一窗口尺寸、同一等待策略）；
  2. Pillow 逐像素差分：平均绝对差、差异像素占比、最大差；
  3. 输出 docs/screenshot-diff/{baseline,candidate,diff}.png 与 report.txt（含结论）。
判据  : 差异像素占比 < (1 - min_similar) 记为 PASS，否则 FAIL。
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "screenshot-diff"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser() -> pathlib.Path:
    for p in EDGE_CANDIDATES:
        if pathlib.Path(p).exists():
            return pathlib.Path(p)
    raise SystemExit("未找到 Edge/Chrome，请安装 Microsoft Edge（WebView2 运行时）后重试。")


def render(browser: pathlib.Path, html_path: pathlib.Path, out_png: pathlib.Path,
           width: int, height: int, budget_ms: int = 4000,
           freeze: bool = False) -> None:
    """无头渲染页面为 PNG。freeze=True 时对两页同等注入动画/过渡禁用样式，
    消除 infinite 动画（如总进度 shimmer）在不同页面渲染时序下的假差异。"""
    target = html_path
    temp = None
    if freeze:
        src = html_path.read_text(encoding="utf-8")
        style = (
            "<style>*{animation:none!important;transition:none!important}"
            ".overall-bar .track i::after{display:none!important}</style>"
        )
        injected = src.replace("<head>", "<head>" + style, 1)
        temp = html_path.with_name(".cmp_freeze_" + html_path.stem + ".html")
        temp.write_text(injected, encoding="utf-8")
        target = temp

    uri = target.resolve().as_uri()
    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        f"--virtual-time-budget={budget_ms}",
        f"--screenshot={str(out_png)}",
        uri,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    finally:
        if temp and temp.exists():
            temp.unlink()
    if not out_png.exists() or out_png.stat().st_size == 0:
        raise SystemExit(f"截图失败: {html_path}")


def diff_images(a_path: pathlib.Path, b_path: pathlib.Path, tolerance: int):
    from PIL import Image, ImageChops

    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    a_rgb = a.load()
    b_rgb = b.load()
    w, h = a.size

    total = w * h
    diff_count = 0
    sum_abs = 0
    max_abs = 0
    min_x = min_y = w
    max_x = max_y = 0

    diff_img = Image.new("RGB", (w, h), (16, 18, 26))
    dpx = diff_img.load()

    for y in range(h):
        for x in range(w):
            pa = a_rgb[x, y]
            pb = b_rgb[x, y]
            d = max(abs(pa[0] - pb[0]), abs(pa[1] - pb[1]), abs(pa[2] - pb[2]))
            sum_abs += d
            if d > max_abs:
                max_abs = d
            if d > tolerance:
                diff_count += 1
                dpx[x, y] = (255, 70, 70)
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y

    mean_abs = sum_abs / total
    pct_diff = diff_count / total * 100.0
    bbox = (min_x, min_y, max_x, max_y) if diff_count else None

    diff_img.save(OUT_DIR / "diff.png")
    return {
        "size": (w, h),
        "mean_abs": round(mean_abs, 4),
        "max_abs": max_abs,
        "diff_pixels": diff_count,
        "pct_diff": round(pct_diff, 4),
        "bbox": bbox,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="求索下载 GUI 前端 · 截图比对校验")
    ap.add_argument("--window", default="1040,800", help="渲染窗口尺寸 WxH")
    ap.add_argument("--tolerance", type=int, default=2, help="单通道像素容差")
    ap.add_argument("--min-similar", type=float, default=0.995,
                    help="最低像素一致率，低于则判 FAIL")
    ap.add_argument("--budget", type=int, default=4000, help="JS 虚拟时间预算 ms")
    ap.add_argument("--no-freeze", action="store_true",
                    help="不冻结动画（默认冻结，避免 shimmer 等时序假差异）")
    args = ap.parse_args()

    w, h = (int(v) for v in args.window.split(","))
    browser = find_browser()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    baseline = ROOT / "ui" / "index.html"
    candidate = ROOT / "index.html"

    print(f"[compare] 浏览器: {browser.name}")
    print(f"[compare] 基准  : {baseline}")
    print(f"[compare] 交付  : {candidate}")
    print("[compare] 渲染中（两页同一窗口/等待策略）…")

    png_b = OUT_DIR / "baseline.png"
    png_c = OUT_DIR / "candidate.png"
    freeze = not args.no_freeze
    render(browser, baseline, png_b, w, h, args.budget, freeze)
    render(browser, candidate, png_c, w, h, args.budget, freeze)

    print("[compare] 逐像素差分中…")
    m = diff_images(png_b, png_c, args.tolerance)
    similar = 1 - m["pct_diff"] / 100.0
    passed = similar >= args.min_similar

    lines = [
        "求索下载 GUI 前端 · 界面截图比对报告",
        "=" * 48,
        f"比对对象 : 基准 ui/index.html（锁定原版） vs 交付 index.html（前端逻辑驱动）",
        f"渲染引擎 : {browser.name} 无头模式（同一尺寸 {m['size'][0]}x{m['size'][1]}、同一 JS 等待策略）",
        f"动画处理 : {'两页同等冻结动画/过渡（消除 shimmer 时序假差异）' if freeze else '未冻结'}",
        f"像素容差 : {args.tolerance} / 通道",
        "",
        "指标",
        "--------",
        f"图像尺寸     : {m['size'][0]} x {m['size'][1]}",
        f"像素总数     : {m['size'][0] * m['size'][1]}",
        f"平均绝对差   : {m['mean_abs']} / 255",
        f"最大通道差   : {m['max_abs']} / 255",
        f"差异像素数   : {m['diff_pixels']}",
        f"差异像素占比 : {m['pct_diff']} %",
        f"像素一致率   : {similar * 100:.4f} %",
        f"差异区域     : {m['bbox'] if m['bbox'] else '无（逐像素一致）'}",
        "",
        "结论",
        "--------",
        f"判定 : {'PASS —— 交付界面与锁定基准 1:1 一致' if passed else 'FAIL —— 存在可见差异，请检查渲染'}",
        f"（判定线：像素一致率 >= {args.min_similar * 100:.1f}%）",
        "",
        "产物",
        "--------",
        f"baseline.png  : 锁定基准截图",
        f"candidate.png : 交付前端截图",
        f"diff.png      : 差异高亮图（红 = 差异像素）",
    ]
    (OUT_DIR / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[compare] 报告已写入: {OUT_DIR / 'report.txt'}")
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
