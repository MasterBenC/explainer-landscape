"""版式渲染层：八种 form（bignum / evidence / list / timeline / relation / sources /
chart / photo）与 FORMS 注册表。每个函数只画"这一镜的主体内容"，chrome 由 kit_chrome 负责。"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

from kit_common import (
    ACCENT, BG, CARD, CONTENT_W, DIM, H, LINE, MARGIN, MUTED, P, RIGHT, TEXT, W,
    _fade_img, _rgb, blend, clamp, count_value, draw_text, ease_out, fit_text, font,
    lift, reveal_text, rrect, text_w, warn_once, wrap,
)


# 双栏证据右栏的可用文字宽：从右栏左边 960 到右边距 RIGHT，一个字都不能多。
QUOTE_W = RIGHT - 960
SOURCES_BOTTOM = 870                    # 片尾来源栏下沿（再往下就是字幕带）


# ---------------------------------------------------------------- 版式
def form_bignum(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    s = sc.get("slots", {})
    p = P(mm, "number", t)
    number, unit = s.get("number", ""), s.get("unit", "")
    color = ACCENT if s.get("emphasis") else TEXT
    size = int(168 * (0.94 + 0.06 * ease_out(p)))
    y = lift(470, p, 24)
    shown = count_value(number, ease_out(p)) if s.get("count") else number
    d.text((MARGIN, y), shown, font=font(size, "bold"), fill=blend(color, min(1.0, p * 1.6)), anchor="la")
    if unit:
        pu = clamp(p * 2 - 0.6)
        dx = text_w(shown, size, "bold") + 14
        d.text((MARGIN + dx, y + 60), unit, font=font(56), fill=blend(TEXT, pu), anchor="la")

    pc = P(mm, "caption", t)
    y2 = 700
    d.line([(MARGIN, y2), (MARGIN + 360 * ease_out(pc), y2)], fill=blend(LINE, pc), width=2)
    if s.get("caption"):
        reveal_text(img, (MARGIN, y2 + 28 + 42), s["caption"], 42, blend(MUTED, 1.0), ease_out(pc))
    if s.get("note"):
        pn = P(mm, "note", t)
        d.text((RIGHT, lift(800, pn, 12)), s["note"], font=font(21), fill=blend(DIM, pn), anchor="ra")


def _placeholder(img, box, label="图片位", p=1.0):
    d = ImageDraw.Draw(img)
    rrect(d, box, 6, fill=blend(CARD, p), outline=blend(LINE, p))
    x0, y0, x1, y1 = box
    d.text(((x0 + x1) / 2, (y0 + y1) / 2), label, font=font(24), fill=blend(DIM, p), anchor="mm")


def form_evidence(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    s = sc.get("slots", {})
    p = P(mm, "image", t)
    lbox, rbox = (134, 470, 900, 840), (960, 470, 1786, 762)
    if s.get("left") and os.path.exists(s["left"]):
        _fade_img(img, lbox, s["left"], p)
        d.rectangle(lbox, outline=blend(LINE, p), width=1)
    else:
        _placeholder(img, lbox, "左：画面 / 人物", p)
    if s.get("right") and os.path.exists(s["right"]):
        _fade_img(img, rbox, s["right"], p)
        d.rectangle(rbox, outline=blend(LINE, p), width=1)
    else:
        _placeholder(img, rbox, "右：截图 / 新闻页", p)
    if s.get("quote"):
        # 右栏的纵向预算只有 762（截图下沿）→ 884（页脚来源行）这 122px：
        # 引文一行 48px + 署名 ~26px 正好，两行引文就必然把署名顶到来源行上。
        # 所以引文只画一行，超宽折行时截尾加省略号并告警（以前是折成两三行硬画，
        # 第二行 828 直接压在署名 826 上——2026-11 评审 P0-3）。
        text = s["quote"]
        lines = wrap(text, 36, QUOTE_W)
        if len(lines) > 1:
            warn_once(f"quote:{sc.get('id')}",
                      f"{sc.get('id')}: slots.quote 一行放不下（右栏 {QUOTE_W}px / 36px，"
                      f"折了 {len(lines)} 行），只画首行加省略号——请缩短引文或拆镜")
            text = fit_text(lines[0] + "…", 36, QUOTE_W)
        draw_text(d, (960, 780), text, 36, blend(TEXT, p), max_w=QUOTE_W)
    if s.get("attrib"):
        pa = P(mm, "attrib", t, p)
        d.text((960, lift(826, pa, 10)), s["attrib"], font=font(22),
               fill=blend(DIM, pa), anchor="la")


def photo_fullbleed(sc) -> bool:
    """这一镜的图片是不是整幅出血（铺满 1920×1080，压在 chrome 下面）。"""
    s = sc.get("slots", {})
    return sc.get("depth") not in ("bg", "split") and not s.get("framed")


def photo_backdrop(img, sc, t, mm):
    """整幅出血图 + 顶部暗带，**背景层**用：必须在 chrome（字幕、章节牌、标题块）之前画。

    老版本把这段塞在 form_photo 里，也就是在 draw_chrome 之后执行——整幅图连带顶部
    暗带会把字幕、章节牌、标题块一起盖掉，全幅 photo 镜等于没有 chrome（P0-1）。
    """
    if sc.get("form") != "photo" or not photo_fullbleed(sc):
        return
    s = sc.get("slots", {})
    src = s.get("image")
    p = P(mm, "image", t)
    if src and os.path.exists(src):
        _fade_img(img, (0, 0, W, H), src, p)
    else:
        _placeholder(img, (0, 0, W, H), "整幅图片位", p)
    if p < 0.999:
        scrim = Image.new("RGB", (W, H), _rgb(BG))
        img.paste(Image.blend(scrim, img.convert("RGB"), p), (0, 0))
    # 暗带是「高度占比」：0.46 表示压住画面顶部 46% 的高度。
    # 老代码写成 int(W * scrim)，在 16:9 画布上等于 883px（82% 高度），字幕区整片压黑（P0-2）。
    band_h = int(H * float(s.get("scrim", 0.46)))
    if band_h > 0:
        overlay = Image.new("RGBA", (W, band_h), (5, 6, 8, 200))
        img.paste(Image.alpha_composite(
            img.crop((0, 0, W, band_h)).convert("RGBA"), overlay).convert("RGB"), (0, 0))


def form_photo(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    s = sc.get("slots", {})
    src = s.get("image")
    p = P(mm, "image", t)
    if sc.get("depth") in ("bg", "split"):
        col_w = (int(W * 0.46) if sc.get("depth") == "bg"
                 else int(W * float(sc.get("split_x", 0.42)))) - MARGIN - 24
        if s.get("caption"):
            pc = P(mm, "caption", t)
            draw_text(d, (MARGIN, lift(640, pc, 12)), s["caption"], 30, blend(MUTED, pc),
                      max_w=col_w)
        if s.get("credit"):
            d.text((900, 818), fit_text(s["credit"], 20, W * 0.46 - 900 - 24),
                   font=font(20), fill=blend(DIM, p), anchor="la")
        return
    if s.get("framed"):
        box = (900, 300, 1786, 800)
        if src and os.path.exists(src):
            _fade_img(img, box, src, p, soften=7)
            ov = Image.new("RGBA", (box[2]-box[0], box[3]-box[1]), (6, 7, 9, 70))
            img.paste(Image.alpha_composite(img.crop(box).convert("RGBA"), ov).convert("RGB"),
                      (box[0], box[1]))
            d.rectangle(box, outline=blend(LINE, p), width=1)
        else:
            _placeholder(img, box, "图片位", p)
        if s.get("caption"):
            pc = P(mm, "caption", t)
            # 框内图的图说只能用到卡片左沿（900）为止，否则文字压在图上。
            draw_text(d, (MARGIN, lift(640, pc, 12)), s["caption"], 30, blend(MUTED, pc),
                      max_w=box[0] - MARGIN - 24)
        if s.get("credit"):
            d.text((900, 818), fit_text(s["credit"], 20, box[0] - 900 + 100),
                   font=font(20), fill=blend(DIM, p), anchor="la")
        return

    # 整幅出血：图与暗带已经由 photo_backdrop() 在背景层画过，这里只补图说与署名。
    if s.get("caption"):
        pc = P(mm, "caption", t)
        draw_text(d, (MARGIN, 700), s["caption"], 32, blend(TEXT, pc), max_w=CONTENT_W)
    if s.get("credit"):
        d.text((MARGIN, 840), fit_text(s["credit"], 20, CONTENT_W),
               font=font(20), fill=blend(MUTED, p), anchor="la")


def form_chart(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    s = sc.get("slots", {})
    kind = s.get("kind", "bar")
    data = s.get("data", [])
    p = P(mm, "chart", t)
    x0, y0, x1, y1 = 900, 470, 1780, 830
    if s.get("chart_title"):
        d.text((x0, y0 - 60), s["chart_title"], font=font(28), fill=blend(MUTED, p), anchor="la")

    if kind == "bar" and data:
        vals = [float(q.get("value", 0)) for q in data]
        mx = max(vals) or 1
        n = len(vals)
        bw = (x1 - x0) / (n * 1.6)
        gap = (x1 - x0 - bw * n) / (n + 1)
        base = y1 - 50
        for i, q in enumerate(data):
            pi = clamp((p - i * 0.12) / 0.7) if p < 1 else 1.0
            pi = ease_out(max(0.0, pi))
            v = float(q.get("value", 0))
            h = (base - y0 - 40) * v / mx * pi
            bx = x0 + gap + i * (bw + gap)
            col = ACCENT if q.get("highlight") else TEXT
            if h > 1:
                rrect(d, (bx, base - h, bx + bw, base), 4, fill=blend(col, pi))
            d.text((bx + bw / 2, base - h - 46), q.get("label", ""), font=font(34, "bold"),
                   fill=blend(TEXT, pi), anchor="mm")
            d.text((bx + bw / 2, base + 18), q.get("name", ""), font=font(24),
                   fill=blend(MUTED, pi), anchor="ma")
        d.line([(x0, base), (x1, base)], fill=blend(LINE, p), width=2)

    elif kind == "line" and data:
        vals = [float(q.get("value", 0)) for q in data]
        mx = max(vals) or 1
        pts = []
        for i, v in enumerate(vals):
            px = x0 + (x1 - x0) * i / max(1, len(vals) - 1)
            py = y1 - 60 - (y1 - y0 - 120) * v / mx
            pts.append((px, py))
        seg = max(1, int(len(pts) * p))
        if seg >= 2:
            d.line(pts[:seg], fill=blend(ACCENT, p), width=4, joint="curve")
        for i, ((px, py), q) in enumerate(zip(pts, data)):
            pp = clamp(p * 1.4 - i * 0.15)
            if pp <= 0:
                continue
            d.ellipse((px - 7, py - 7, px + 7, py + 7), fill=blend(ACCENT, pp))
            d.text((px, py - 30), q.get("label", ""), font=font(28, "bold"), fill=blend(TEXT, pp), anchor="mb")
            d.text((px, y1 - 20), q.get("name", ""), font=font(22), fill=blend(MUTED, pp), anchor="ma")

    elif kind == "donut" and data:
        cx, cy, r, thick = (x0 + x1) / 2, (y0 + y1) / 2, 150, 46
        total = sum(float(q.get("value", 0)) for q in data) or 1
        start = -90
        for q in data:
            ext = 360 * float(q.get("value", 0)) / total * p
            col = ACCENT if q.get("highlight") else "#3A3F46"
            if ext > 0.5:
                d.arc((cx - r, cy - r, cx + r, cy + r), start, start + ext, fill=blend(col, p), width=thick)
            mid = math.radians(start + ext / 2)
            lx, ly = cx + (r + 60) * math.cos(mid), cy + (r + 60) * math.sin(mid)
            if ext > 2:
                d.text((lx, ly), f'{q.get("label","")} {q.get("value","")}%', font=font(24),
                       fill=blend(TEXT if q.get("highlight") else MUTED, p), anchor="mm")
            start += ext

    elif kind == "kpi" and data:
        y = y0 + 30
        for i, q in enumerate(data):
            pp = clamp((p - i * 0.15) / 0.7)
            pp = ease_out(max(0.0, pp))
            yy = lift(y, pp, 16)
            d.text((x0, yy), q.get("label", ""), font=font(24), fill=blend(MUTED, pp), anchor="la")
            d.text((x0, yy + 34), q.get("value", ""), font=font(64, "bold"),
                   fill=blend(ACCENT if q.get("highlight") else TEXT, pp), anchor="la")
            if q.get("name"):
                d.text((x0 + 420, yy + 62), q["name"], font=font(22), fill=blend(DIM, pp), anchor="la")
            y += 130

    if s.get("source_note"):
        d.text((x1, 860), s["source_note"], font=font(20), fill=blend(DIM, p), anchor="ra")


def form_list(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    s = sc.get("slots", {})
    items = s.get("items", [])
    has_media = bool(s.get("media") and os.path.exists(s["media"]))
    # 条目文字只能用到右栏图位左边沿（或整幅右边距）为止；老版不折行，长句直接冲到画外。
    avail = (1180 - 44 - 236) if has_media else (RIGHT - 236)
    y = 470
    for i, it in enumerate(items):
        p = P(mm, f"items[{i}]", t, 0.0)
        if p <= 0.001:
            continue
        pe = ease_out(p)
        yy = lift(y, pe, 22)
        dx = -40 * (1 - pe)                       # 从左滑入
        d.rectangle((134 + dx, yy + 6, 138 + dx, yy + 6 + 40 * pe), fill=blend(ACCENT, pe))
        d.text((162 + dx, yy), it.get("n", f"0{i + 1}"), font=font(28, "mono"),
               fill=blend(ACCENT, pe), anchor="la")
        lines = wrap(it.get("text", ""), 32, avail) or [""]
        for j, ln in enumerate(lines):
            reveal_text(img, (236 + dx, yy + 32 + j * 43), ln, 32, TEXT, pe)
        y += max(84, len(lines) * 43 + 26)        # 折成两行的条目自己往下让位，不压下一行
    if has_media:
        pm = P(mm, "media", t, P(mm, "items[0]", t) if items else 1.0)
        box = (1180, 470, 1786, 800)
        _fade_img(img, box, s["media"], pm)
        d.rectangle(box, outline=blend(LINE, pm), width=1)


def form_timeline(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    s = sc.get("slots", {})
    pts = s.get("points", [])
    x0, x1 = 134, 1180
    y0, y1 = 500, 760
    for i, q in enumerate(pts):
        p = P(mm, f"points[{i}]", t, 0.0)
        if p <= 0.001:
            continue
        y = y0 + (y1 - y0) * i / max(1, len(pts) - 1)
        if i > 0:
            yp = y0 + (y1 - y0) * (i - 1) / max(1, len(pts) - 1)
            d.line([(x0 + 40, yp), (x0 + 40 + (x1 - x0 - 240) * p, y)], fill=blend(LINE, p), width=2)
        d.ellipse((x0 + 32, y - 8, x0 + 48, y + 8), fill=blend(ACCENT, p))
        d.text((x0, y - 44), q.get("label", ""), font=font(26), fill=blend(MUTED, p), anchor="la")
        d.text((x0 + 80, y - 26), q.get("value", ""), font=font(40, "bold"), fill=blend(TEXT, p), anchor="la")
    if s.get("delta"):
        pd = P(mm, "delta", t, P(mm, "points[1]", t) if len(pts) > 1 else 1.0)
        d.text((x1 - 300, 560), s["delta"], font=font(64, "bold"), fill=blend(ACCENT, pd), anchor="la")


def form_relation(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    s = sc.get("slots", {})
    cx, cy = 960, 620
    sat = s.get("satellites", [])
    pc = P(mm, "center", t)
    if s.get("center"):
        bw = max(200, int(text_w(s["center"], 36, "bold")) + 60)
        rrect(d, (cx - bw // 2, cy - 34, cx + bw // 2, cy + 34), 34, fill=blend(TEXT, pc))
        d.text((cx, cy), s["center"], font=font(36, "bold"), fill=blend(BG, pc), anchor="mm")
    r = 300
    for i, q in enumerate(sat):
        p = P(mm, f"satellites[{i}]", t, 0.0)
        if p <= 0.001:
            continue
        ang = -math.pi / 2 + i * 2 * math.pi / max(1, len(sat))
        px, py = cx + r * math.cos(ang) * 1.35, cy + r * math.sin(ang) * 0.75
        gx, gy = cx + (px - cx) * p, cy + (py - cy) * p
        d.line([(cx, cy), (gx, gy)], fill=blend(LINE, p), width=1)
        bw = max(120, int(text_w(q.get("label", ""), 30)) + 40)
        rrect(d, (px - bw / 2, py - 26, px + bw / 2, py + 26), 26,
              fill=blend(CARD, p), outline=blend(LINE, p))
        d.text((px, py), q.get("label", ""), font=font(30), fill=blend(TEXT, p), anchor="mm")


def form_sources(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    s = sc.get("slots", {})
    pcl = P(mm, "closing", t)
    y = 380
    for ln in wrap(s.get("closing", ""), 88, 900, "bold")[:2]:
        reveal_text(img, (MARGIN, y + 88), ln, 88, TEXT, ease_out(pcl), weight="bold")
        y += int(88 * 1.25)
    pb = P(mm, "blocks", t)
    d.line([(1180, 200), (1180, 200 + 660 * ease_out(pb))], fill=blend(LINE, pb), width=1)
    y = 210
    cut = 0                                          # 撞到安全线后被丢掉的行数
    for j, block in enumerate(s.get("blocks", [])):
        pj = clamp((pb - j * 0.12) / 0.88) if pb < 1 else 1.0
        if pj <= 0:
            continue
        if block.get("title"):
            d.text((1226, y), block["title"], font=font(24, "bold"), fill=blend(MUTED, pj), anchor="la")
            y += 44
        for line in block.get("lines", []):
            for k, ln in enumerate(wrap(line, 21, 540)[:2]):
                if y > SOURCES_BOTTOM:               # 再画就压到字幕带上了
                    cut += 1
                    continue
                pl = clamp(pj * 1.3 - k * 0.1)
                d.text((1226 + 12 * (1 - pl), y), ln, font=font(21), fill=blend(DIM, pl), anchor="la")
                y += 34
        y += 16
    if cut:
        # 片尾来源页只有 210..870 这一栏；切极简档会把逐镜 source 全并进来，容易撞线。
        # 以前是默默画到画面外，现在至少说一声：哪些行没上屏。
        warn_once(f"sources:{sc.get('id')}",
                  f"片尾来源 {cut} 行超出安全线（y>{SOURCES_BOTTOM}）没上屏，"
                  f"请精简 blocks 或拆到多镜")


FORMS = {
    "bignum": form_bignum, "evidence": form_evidence, "list": form_list,
    "timeline": form_timeline, "relation": form_relation, "sources": form_sources,
    "photo": form_photo, "chart": form_chart,
}


# 需要先铺到背景层（chrome 之下）的版式。旧版把整幅图放在 FORMS 里画，结果是字幕和
# 章节牌被自己的配图盖住——所以这些版式的底图走这里，主体内容仍走 FORMS。
BACKDROPS = {"photo": photo_backdrop}
