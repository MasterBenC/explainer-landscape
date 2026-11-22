#!/usr/bin/env python3
"""生成示例用的占位素材（纯 Pillow，ASCII 文本，不依赖中文字体）。

    python assets/examples/make_media.py

产出：
    media/doc-page.png      白底「公告 / 声明页」，给 photo framed、evidence 右栏用
    media/archive-card.png  偏黄的旧资料卡，给 depth bg / fg、archival 演示用

这些图只是占位：真片子里换成自己的截图 / 现场图，并在 `source` / `credit`
里写清机构 + 日期。
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(HERE, "media")

INK = (24, 26, 30)
MUTED = (110, 114, 120)
RULE = (206, 208, 212)
RED = (224, 50, 44)


def _para(d, x, y, w, lines, lh=16, color=MUTED):
    for i in range(lines):
        ln = w - (i * 37) % 120
        d.rounded_rectangle((x, y + i * lh, x + ln, y + i * lh + 7), 3, fill=color)


def doc_page(path):
    W, H = 1000, 620
    im = Image.new("RGB", (W, H), (250, 250, 248))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 74), fill=(238, 238, 235))
    d.text((44, 26), "INVESTOR RELATIONS  /  STATEMENT", fill=INK)
    d.text((W - 190, 26), "2026-11-13", fill=MUTED)
    d.line((44, 120, W - 44, 120), fill=RULE, width=2)
    d.text((44, 146), "Board statement", fill=INK)
    _para(d, 44, 188, 520, 2, 22, (60, 63, 68))
    d.line((44, 236, W - 44, 236), fill=RULE, width=1)
    for k in range(4):
        _para(d, 44, 268 + k * 78, 900, 4, 15)
    d.rectangle((44, 560, 190, 590), fill=RED)
    d.text((58, 569), "NO REASON GIVEN", fill=(255, 255, 255))
    im.save(path)


def archive_card(path):
    W, H = 1400, 760
    paper = Image.new("RGB", (W, H), (232, 223, 203))
    d = ImageDraw.Draw(paper)
    for y in range(0, H, 34):
        d.line((0, y, W, y), fill=(224, 214, 193), width=1)
    # 照片区：一块噪点灰，代表"当年的现场照"
    photo = Image.new("RGB", (560, 380), (120, 122, 118))
    pd = ImageDraw.Draw(photo)
    for i in range(0, 560, 7):
        pd.line((i, 0, i + 120, 380), fill=(132 + i % 17, 134 + i % 13, 128 + i % 11))
    photo = photo.filter(ImageFilter.GaussianBlur(2))
    paper.paste(photo, (64, 96))
    d = ImageDraw.Draw(paper)
    d.text((64, 52), "ARCHIVE  ·  1996", fill=(70, 58, 42))
    d.text((664, 110), "First issuing day", fill=(60, 50, 36))
    _para(d, 664, 150, 620, 5, 26, (128, 114, 92))
    d.line((64, 516, W - 64, 516), fill=(176, 162, 138), width=2)
    d.text((64, 542), "CASE 01  ·  PLACEHOLDER  ·  1996-04-18", fill=(110, 96, 76))
    paper.save(path)


def main() -> int:
    os.makedirs(MEDIA, exist_ok=True)
    doc_page(os.path.join(MEDIA, "doc-page.png"))
    archive_card(os.path.join(MEDIA, "archive-card.png"))
    for name in ("doc-page.png", "archive-card.png"):
        print(f"-> {os.path.join(MEDIA, name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
