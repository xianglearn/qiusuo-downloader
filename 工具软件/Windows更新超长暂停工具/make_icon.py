# -*- coding: utf-8 -*-
"""生成应用图标 app.ico

设计：蓝色圆角方块 + 白色"暂停"双竖条；
大尺寸再加一圈白色细环 / 断口圆环，表达"更新循环被截停"。

每个尺寸独立超采样渲染，保证 16x16 下依然清晰；
小尺寸自动去掉圆环、加粗竖条，避免糊成一团。

用法：python make_icon.py            # 出终稿 app.ico
     python make_icon.py --compare  # 出 4 个方案对比图供挑选
"""

from __future__ import annotations

import io
import math
import struct

from PIL import Image, ImageDraw, ImageFilter

# ---------------- 设计参数 ----------------
TOP = (94, 151, 255)      # 渐变顶部（亮蓝）
BOT = (23, 58, 178)       # 渐变底部（深蓝）
CORNER = 0.225            # 圆角半径占边长比例
SUPER = 8                 # 超采样倍数

ICO_SIZES = (256, 128, 96, 64, 48, 40, 32, 24, 20, 16)


def _tier(size: int) -> str:
    """按分辨率分档做"渐进简化"，这是多尺寸图标的惯用做法：

    - 96 以上：断口圆环 + 箭头（细节全给，读作"更新循环被截停"）
    - 48~64 ：断口圆环（箭头在这个尺寸会糊成噪点，去掉）
    - 40 以下：只留加粗暂停竖条（再小就糊成一团了）
    """
    if size >= 96:
        return "arrow"
    if size >= 48:
        return "arc"
    return "none"


def _gradient(size: int) -> Image.Image:
    """竖向线性渐变，用 1×N 的图拉伸，避免逐像素画整张图。"""
    col = Image.new("RGB", (1, size))
    for y in range(size):
        t = (y / max(1, size - 1)) ** 0.85
        col.putpixel((0, y), tuple(
            int(TOP[i] + (BOT[i] - TOP[i]) * t) for i in range(3)))
    return col.resize((size, size), Image.BILINEAR)


def _ring(draw: ImageDraw.ImageDraw, s: float, *, alpha: int, width: float,
          radius: float, gap_deg: float, arrow: bool) -> None:
    """在透明层上画外环。

    注意：ImageDraw 画在 RGBA 图上是直接覆盖、不做混合的，
    所以带透明的元素必须先画到独立透明层再 alpha_composite，
    否则白色半透明会变成灰色（踩过这个坑）。
    """
    cx = cy = s / 2
    r = s * radius
    w = max(1.5, s * width)
    ink = (255, 255, 255, alpha)

    if gap_deg <= 0:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ink, width=round(w))
        return

    # PIL 角度：0°=3 点钟方向，顺时针为正；270°=12 点钟方向。
    # 缺口留在正上方：从"缺口末端"顺时针扫到"缺口始端"。
    # 注意 end < start 时 PIL 会自动补 360，所以这样写得到的是
    # (360 - gap_deg) 那段长弧，而不是缺口本身（这个坑踩过一次）。
    gap_start = 270.0 - gap_deg / 2.0
    gap_end = 270.0 + gap_deg / 2.0
    draw.arc([cx - r, cy - r, cx + r, cy + r],
             start=gap_end, end=gap_start, fill=ink, width=round(w))

    if not arrow:
        return

    # 在圆弧收尾处（缺口左端）加一个箭头，读作"刷新/循环"
    a = math.radians(gap_start)
    px, py = cx + r * math.cos(a), cy + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)        # 顺时针切向
    nx, ny = math.cos(a), math.sin(a)         # 径向
    tip = (px + tx * w * 1.9, py + ty * w * 1.9)
    b1 = (px - tx * w * 0.7 + nx * w * 0.9, py - ty * w * 0.7 + ny * w * 0.9)
    b2 = (px - tx * w * 0.7 - nx * w * 0.9, py - ty * w * 0.7 - ny * w * 0.9)
    draw.polygon([tip, b1, b2], fill=ink)


def render(size: int, variant: str = "auto") -> Image.Image:
    """渲染单个尺寸的 RGBA 图标。variant 传 auto 时按尺寸自动分档。"""
    if variant == "auto":
        variant = _tier(size)

    s = size * SUPER
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 1) 圆角底 + 渐变
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=int(s * CORNER), fill=255)
    img.paste(_gradient(s), (0, 0), mask)

    # 2) 左上柔光，让平面渐变有体积感
    glow = Image.new("L", (s, s), 0)
    ImageDraw.Draw(glow).ellipse(
        [-s * 0.62, -s * 1.10, s * 0.92, s * 0.16], fill=54)
    glow = glow.filter(ImageFilter.GaussianBlur(s * 0.09))
    glow = Image.composite(glow, Image.new("L", (s, s), 0), mask)
    img = Image.alpha_composite(
        img, Image.merge("RGBA", (glow.point(lambda v: 255),) * 3 + (glow,)))

    # 3) 半透明元素画到独立透明层，再整体合成（否则不混合、发灰）
    overlay = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    if variant == "ring":
        _ring(od, s, alpha=70, width=0.045, radius=0.400, gap_deg=0.0, arrow=False)
    elif variant == "arc":
        _ring(od, s, alpha=92, width=0.052, radius=0.378, gap_deg=72.0, arrow=False)
    elif variant == "arrow":
        _ring(od, s, alpha=92, width=0.052, radius=0.378, gap_deg=78.0, arrow=True)

    # 4) 暂停双竖条（纯白不透明，直接画主图上即可）
    if variant == "none":
        bar_w, gap, bar_h = s * 0.195, s * 0.110, s * 0.560
    else:
        bar_w, gap, bar_h = s * 0.160, s * 0.100, s * 0.440

    cx = cy = s / 2
    for sign in (-1, 1):
        bx = cx + sign * (gap / 2 + bar_w / 2)
        od.rounded_rectangle(
            [bx - bar_w / 2, cy - bar_h / 2, bx + bar_w / 2, cy + bar_h / 2],
            radius=bar_w / 2, fill=(255, 255, 255, 255))

    img = Image.alpha_composite(img, overlay)
    return img.resize((size, size), Image.LANCZOS)


def write_ico(path: str, sizes=ICO_SIZES, variant: str = "auto") -> None:
    """手动写 ICO 容器：每个尺寸塞一张 PNG（Vista 之后都支持）。"""
    blobs = []
    for s in sizes:
        buf = io.BytesIO()
        render(s, variant).save(buf, "PNG", optimize=True)
        blobs.append((s, buf.getvalue()))

    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, body = b"", b""
    for s, payload in blobs:
        dim = 0 if s >= 256 else s          # ICO 里 256 用 0 表示
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                               len(payload), offset)
        offset += len(payload)
        body += payload
    with open(path, "wb") as f:
        f.write(header + entries + body)


def write_preview(path: str, variant: str = "auto",
                  label: str = "") -> None:
    """深色背景预览：大图 + 各尺寸 1:1 对照 + 任务栏效果。"""
    bg = (32, 35, 42)
    canvas = Image.new("RGB", (760, 400), bg)
    d = ImageDraw.Draw(canvas)

    big = render(224, variant)
    canvas.paste(big, (40, 60), big)

    if label:
        d.text((40, 30), label, fill=(150, 156, 168))

    x = 330
    for sz in (96, 64, 48, 32, 16):
        ic = render(sz, variant)
        canvas.paste(ic, (x, 60 + (224 - sz) // 2), ic)
        x += sz + 20

    bar = Image.new("RGB", (320, 44), (26, 28, 34))
    for sz, bx in ((24, 14), (16, 50), (32, 84)):
        ic = render(sz, variant)
        bar.paste(ic, (bx, (44 - sz) // 2), ic)
    canvas.paste(bar, (330, 220))
    d.rectangle([329, 219, 650, 264], outline=(66, 70, 80))
    d.text((330, 278), "任务栏 24 / 16 / 32 实际大小", fill=(120, 126, 138))

    canvas.save(path)


def write_compare(path: str) -> None:
    """4 个方案并排，用来挑设计。"""
    variants = [("none", "方案A：纯暂停竖条"),
                ("ring", "方案B：细闭合圆环"),
                ("arc", "方案C：断口圆环"),
                ("arrow", "方案D：断口圆环 + 箭头")]
    cell_w, cell_h = 380, 300
    canvas = Image.new("RGB", (cell_w * 2, cell_h * 2), (32, 35, 42))
    d = ImageDraw.Draw(canvas)
    for i, (v, name) in enumerate(variants):
        ox, oy = (i % 2) * cell_w, (i // 2) * cell_h
        d.rectangle([ox, oy, ox + cell_w - 1, oy + cell_h - 1],
                    outline=(58, 62, 72))
        d.text((ox + 14, oy + 12), name, fill=(160, 166, 178))
        big = render(168, v)
        canvas.paste(big, (ox + 20, oy + 46), big)
        x = ox + 210
        for sz in (48, 32, 16):
            ic = render(sz, v)
            canvas.paste(ic, (x, oy + 46 + (168 - sz) // 2), ic)
            x += sz + 16
    canvas.save(path)


if __name__ == "__main__":
    import sys

    if "--compare" in sys.argv:
        write_compare("icon_compare.png")
        print("已生成 icon_compare.png")
    else:
        write_ico("app.ico")
        write_preview("icon_preview.png", label="终稿 · 按分辨率自动分档")
        print("已生成 app.ico 与 icon_preview.png")
        print("尺寸:", ", ".join(str(s) for s in ICO_SIZES))
