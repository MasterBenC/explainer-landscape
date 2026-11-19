"""单镜合成层：depth 的三种落法（bg / split / fg）+ 按 chrome → 标题块 → 版式 →
证据标注 → 横条的顺序组装一帧，返回 PIL Image。"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

from kit_chrome import draw_callouts, draw_chrome, draw_kicker_block, draw_strap
from kit_common import (
    W, H, P, _IMG_CACHE, _load, _paste, archival, base_background, draw_backdrop,
    ease_out, motion_map,
)
from kit_forms import FORMS


def render_scene(sc, t=None, spec_brand=None):
    img = base_background().copy()
    if spec_brand and not sc.get("brand"):
        sc = {**sc, "brand": spec_brand}
    mm = motion_map(sc)
    if t is None:
        t = 999.0
    dur = float(sc.get("dur", 6))

    bg_path = sc.get("bg")
    depth = sc.get("depth", "bg")
    if bg_path and os.path.exists(bg_path) and depth == "bg":
        draw_backdrop(img, bg_path, sc, min(t, dur), dur)
        # 文字侧压暗：默认左侧渐深，图表镜整体压暗
        scrim = sc.get("scrim", [0.0, 0.72])
        if isinstance(scrim, (int, float)):
            scrim = [0.0, float(scrim)]
        strength = float(scrim[1])
        if strength > 0:
            ov = Image.new("RGBA", (W, H), (4, 5, 7, int(255 * strength)))
            img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        # 左侧竖向暗带，保证文字可读
        band = int(W * 0.46)
        grad = _IMG_CACHE.get(("band", band))
        if grad is None:
            grad = Image.new("RGBA", (band, H))
            gd = ImageDraw.Draw(grad)
            for x in range(band):
                a = int(210 * (1 - x / band) ** 1.2)
                gd.line([(x, 0), (x, H)], fill=(5, 6, 8, a))
            _IMG_CACHE[("band", band)] = grad
        img.paste(Image.alpha_composite(img.crop((0, 0, band, H)).convert("RGBA"),
                                        grad).convert("RGB"), (0, 0))
    elif bg_path and os.path.exists(bg_path) and depth == "split":
        # 左实色栏放文字，右侧整幅清晰图，互不覆盖
        split_x = int(sc.get("split_x", 0.42) * W)
        img.paste(Image.new("RGB", (split_x, H), (10, 11, 15)), (0, 0))
        tile = _load(bg_path)
        crop = sc.get("crop") or {}
        zoom = float(crop.get("zoom", 1.10))
        bw, bh = int(tile.width * zoom), int(tile.height * zoom)
        big = tile.resize((bw, bh), Image.BILINEAR)
        fw, fh = W - split_x, H
        cx = float(crop.get("cx", 0.5)) * (bw - fw)
        cy = float(crop.get("cy", 0.5)) * (bh - fh)
        left = int(max(0, min(bw - fw, cx)))
        top = int(max(0, min(bh - fh, cy)))
        img.paste(big.crop((left, top, left + (W - split_x), top + H)), (split_x, 0))
        # 底部字幕带压暗，字幕压在图上也能读
        strip = _IMG_CACHE.get(("strip",))
        if strip is None:
            strip = Image.new("RGBA", (W, 220))
            sd = ImageDraw.Draw(strip)
            for yy in range(220):
                a = int(215 * (yy / 219) ** 0.8)
                sd.line([(0, yy), (W, yy)], fill=(6, 7, 9, a))
            _IMG_CACHE[("strip",)] = strip
        img.paste(Image.alpha_composite(img.crop((0, H - 220, W, H)).convert("RGBA"), strip).convert("RGB"),
                  (0, H - 220))
        d1 = ImageDraw.Draw(img)
        d1.line([(split_x, 0), (split_x, H)], fill=(38, 40, 46), width=2)
    elif bg_path and os.path.exists(bg_path) and depth == "fg":
        # 前景层：图做成一块浮在暗底上的档案卡片，文字压在上面
        img = archival(img, sc, t, seed=sum(ord(c) for c in sc.get("id", "x")) % 6)
        box = (880, 170, 1770, 880)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (box[0] + 16, box[1] + 26, box[2] + 16, box[3] + 26), 6, fill=(0, 0, 0, 190))
        shadow = shadow.filter(ImageFilter.GaussianBlur(28))
        img = Image.alpha_composite(img.convert("RGBA"), shadow).convert("RGB")
        p = ease_out(P(mm, "image", t))
        zoom = 1.04 - 0.04 * p
        bw, bh = int((box[2] - box[0]) * zoom), int((box[3] - box[1]) * zoom)
        fk = ("fg", sc.get("id"), bg_path, bw, bh)
        tile = _IMG_CACHE.get(fk)
        if tile is None:
            raw = _paste(bg_path, (0, 0, bw, bh))
            tile = archival(raw, sc, t, seed=sum(ord(c) for c in sc.get("id", "x")) % 6)
            _IMG_CACHE[fk] = tile
        dx = int(30 * (1 - p))
        img.paste(tile, (box[0] + (bw - (box[2] - box[0])) // 2 - dx,
                         box[1] + (bh - (box[3] - box[1])) // 2 - 10))
        d1 = ImageDraw.Draw(img)
        d1.rectangle(box, outline=(120, 120, 120), width=1)

    draw_chrome(img, sc, t, mm)
    draw_kicker_block(img, sc, t, mm)
    fn = FORMS.get(sc.get("form", "bignum"))
    if fn is None:
        raise SystemExit(f"未知版式: {sc.get('form')}")
    fn(img, sc, t, mm)
    draw_callouts(img, sc, t, mm)
    draw_strap(img, sc, t, mm)
    return img
