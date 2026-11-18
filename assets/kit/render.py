#!/usr/bin/env python3
"""explainer-landscape 渲染器 v3：spec.json -> 带动效的 16:9 画面。

每个元素都有入场时间。渲染函数接受场景内时间 t，输出该时刻的帧；
t 缺省时给最终状态（出静帧用）。

    python render.py spec.json out/ --png                 # 每镜终帧
    python render.py spec.json out/ --contact             # 拼图（旧名 --floorplan 仍可用）
    python render.py spec.json out/ --mp4                 # 每镜一段带动效的 mp4（剪辑用）
    python render.py spec.json out/ --video final.mp4     # 整片（转场在渲染器内合成）

`--video` 走 render_film：逐帧合成转场，**总时长严格等于各镜 dur 之和**，
不用 ffmpeg xfade，所以没有"每次转场吃掉一个转场时长"的问题，也不绑定 ffmpeg 版本。
`--mp4` 只出分镜片段（不含转场），留给剪辑软件自己拼。

字段全表见 references/spec-schema.md；动效语法见 references/motion-spec.md。
没有写 motion 的场景，按版式自动分配入场时间（章节牌 0s、标题 0.12s、主体 0.3s 起）。
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- 设计 token
W, H = 1920, 1080
BG = "#07080A"
TEXT = "#F2F2F2"
MUTED = "#9BA1A8"
DIM = "#6C7177"
ACCENT = "#E0322C"
LINE = "#2A2C30"
CARD = "#101216"

MARGIN = 134
RIGHT = 1786
CONTENT_W = RIGHT - MARGIN
FPS = 30          # 兜底值：横版优先 30fps。spec 里写 canvas.fps 就以 spec 为准

FONT_CANDIDATES = {
    "regular": [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\Deng.ttf",
                "/System/Library/Fonts/PingFang.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],
    "bold": [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf",
             "/System/Library/Fonts/PingFang.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"],
    "mono": [r"C:\Windows\Fonts\consola.ttf", "/System/Library/Fonts/Menlo.ttc",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
}
_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key in _cache:
        return _cache[key]
    for path in FONT_CANDIDATES.get(weight, []):
        if os.path.exists(path):
            f = ImageFont.truetype(path, size)
            _cache[key] = f
            return f
    # regular / bold 找不到任何中文字体时不能静默回退：load_default 没有 CJK 字形，
    # 会渲成 □□□ 且退出码仍是 0（2026-11 评审 C5，比报错更难查）。
    if weight in ("regular", "bold"):
        sys.stderr.write(
            "ERROR: 找不到中文字体，中文会渲成方框。\n"
            "  试过：" + "、".join(FONT_CANDIDATES.get(weight, [])) + "\n"
            "  Linux: apt install fonts-noto-cjk\n"
            "  macOS: 安装「苹方」或把 NotoSansCJK 放到 /usr/share/fonts/opentype/noto/\n"
            "  Windows: 确认 C:\\Windows\\Fonts\\msyh.ttc 存在（微软雅黑）\n")
        raise SystemExit(2)
    f = ImageFont.load_default(size)
    _cache[key] = f
    return f


# ---------------------------------------------------------------- 动效工具
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(p):
    return 1 - (1 - p) ** 3


def ease_in_out(p):
    return 3 * p * p - 2 * p * p * p


def prog(t, start, dur, ease="out"):
    """t 时刻，从 start 开始、dur 长的动画进度（0-1）。"""
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    p = clamp((t - start) / dur)
    if ease == "out":
        return ease_out(p)
    if ease == "in_out":
        return ease_in_out(p)
    if ease == "instant":
        return 1.0 if t >= start else 0.0
    return p


def blend(color, p, bg=BG):
    """把颜色按 p 混向背景色，模拟淡入（比 RGBA 合成快得多）。"""
    if p >= 0.999:
        return color
    if p <= 0.001:
        return bg
    c = _rgb(color)
    b = _rgb(bg)
    return "#%02x%02x%02x" % tuple(int(c[i] * p + b[i] * (1 - p)) for i in range(3))


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lift(y, p, dist=14):
    """入场时从下方 dist 抬到位。"""
    return y + dist * (1 - p)


def spring(p, freq=3.0, damp=6.0):
    p = clamp(p)
    if p >= 1:
        return 1.0
    return 1 - math.exp(-damp * p) * math.cos(freq * 2 * math.pi * p)


def reveal_text(img, xy, s, size, color, p, weight="regular", anchor="la"):
    """遮罩揭示：文字从左往右刷出来（比淡入更有"信息在写入"的感觉）。"""
    if p <= 0.001 or not s:
        return
    f = font(size, weight)
    tw = max(1, int(f.getlength(s)))
    layer = Image.new("RGBA", (tw + 4, int(size * 1.6)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((0, int(size * 1.2)), s, font=f, fill=color, anchor="ls")
    cut = int(tw * clamp(p))
    if cut <= 0:
        return
    layer = layer.crop((0, 0, cut, layer.height))
    img.paste(Image.alpha_composite(
        img.crop((int(xy[0]), int(xy[1] - size * 1.2),
                  int(xy[0]) + cut, int(xy[1] - size * 1.2) + layer.height)).convert("RGBA"),
        layer).convert("RGB"), (int(xy[0]), int(xy[1] - size * 1.2)))


def count_value(target, p):
    """数字滚动：把 target（可能带单位/符号）解析成数值，按 p 从 0 滚到目标。

    只在槽位写了 `"count": true` 时才走这里；常规版式禁用 count-up。
    """
    import re
    m = re.match(r"^([^\d\-+]*)(-?[\d,]+(?:\.\d+)?)(.*)$", str(target))
    if not m:
        return str(target)
    pre, num, post = m.groups()
    if p >= 0.999:
        return str(target)
    val = float(num.replace(",", "")) * p
    digits = len(num.split(".")[1]) if "." in num else 0
    out = f"{val:,.{digits}f}" if digits else f"{round(val):,}"
    return pre + out + post


_GRAIN = {}


def grain_tiles(n=6, size=(W, H)):
    """预生成几张胶片颗粒，逐帧轮换用——这是"档案感"和持续微动的来源。"""
    if n in _GRAIN:
        return _GRAIN[n]
    import random
    tiles = []
    rnd = random.Random(20261113)
    for _ in range(n):
        small = Image.new("L", (size[0] // 3, size[1] // 3))
        px = small.load()
        for y in range(small.height):
            for x in range(small.width):
                px[x, y] = rnd.randint(96, 160)
        tiles.append(small.resize(size, Image.BILINEAR))
    _GRAIN[n] = tiles
    return tiles


def archival(img, sc, t, seed=0):
    """档案化处理：去饱和 → 暖调 → 压暗角 → 颗粒 → 轻微门 liner 抖动。"""
    p = sc.get("archival") if isinstance(sc.get("archival"), dict) else {}
    desat = float(p.get("desat", 0.62))
    warm = float(p.get("warm", 1.0))
    dark = float(p.get("dark", 0.0))
    if desat > 0:
        gray = img.convert("L").convert("RGB")
        img = Image.blend(img, gray, desat)
    if warm != 1.0 or dark:
        r, g, b = img.split()
        r = r.point(lambda v: min(255, int(v * warm * (1 - dark) + 8 * dark)))
        g = g.point(lambda v: min(255, int(v * (0.99) * (1 - dark) + 6 * dark)))
        b = b.point(lambda v: min(255, int(v * (0.90) * (1 - dark))))
        img = Image.merge("RGB", (r, g, b))
    tiles = grain_tiles()
    tile = tiles[seed % len(tiles)]
    if tile.size != img.size:
        tile = tile.crop((0, 0, min(tile.width, img.width), min(tile.height, img.height))).resize(
            img.size, Image.BILINEAR)
    img = Image.blend(img, Image.merge("RGB", (tile, tile, tile)), 0.022)
    return img


_BD_CACHE = {}


def _prepare_backdrop(path, sc):
    """每个镜头只做一次羽化预处理（降采样毁字 + 模糊），之后逐帧只做裁剪。"""
    key = (path, sc.get("blur", 0), sc.get("id", ""))
    if key in _BD_CACHE:
        return _BD_CACHE[key]
    zoom = 1.14
    bw, bh = int(W * zoom), int(H * zoom)
    tile = _paste(path, (0, 0, bw, bh))
    blur = float(sc.get("blur", 0))
    if blur > 0:
        tile = tile.filter(ImageFilter.GaussianBlur(blur))
    tile = archival(tile, sc, 0, seed=sum(ord(c) for c in sc.get("id", "x")) % 6)
    _BD_CACHE[key] = tile
    return tile


def draw_backdrop(img, path, sc, t, dur):
    """全幅背景：预处理过的底图 + 极缓平移裁切。"""
    if not path or not os.path.exists(path):
        return False
    tile = _prepare_backdrop(path, sc)
    p = clamp(t / max(0.1, dur))
    left = (tile.width - W) // 2 - int(14 * p) + 7
    top = (tile.height - H) // 2 - int(8 * p) + 4
    left = max(0, min(tile.width - W, left))
    top = max(0, min(tile.height - H, top))
    img.paste(tile.crop((left, top, left + W, top + H)), (0, 0))
    return True


_BG_CACHE = {}


def base_background():
    """静态底：近黑 #07080A，上沿略亮一点点，四周压暗。只生成一次。"""
    if "bg" in _BG_CACHE:
        return _BG_CACHE["bg"]
    top, bottom = (10, 12, 16), (5, 6, 8)
    col = Image.new("RGB", (1, H))
    px = col.load()
    for y in range(H):
        p = y / max(1, H - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * p) for i in range(3))
    bg = col.resize((W, H), Image.BILINEAR)
    vig = Image.new("L", (W, H), 0)
    dv = ImageDraw.Draw(vig)
    dv.ellipse((-W * 0.15, -H * 0.2, W * 1.15, H * 1.2), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(140))
    dark = Image.new("RGB", (W, H), (3, 4, 5))
    bg = Image.composite(bg, dark, vig)
    _BG_CACHE["bg"] = bg
    return bg


# ---------------------------------------------------------------- 文本
def text_w(s: str, size: int, weight: str = "regular") -> float:
    return font(size, weight).getlength(s)


def wrap(s: str, size: int, max_w: float, weight: str = "regular") -> list[str]:
    if not s:
        return []
    lines, cur = [], ""
    for ch in s:
        trial = cur + ch
        if text_w(trial, size, weight) <= max_w or not cur:
            cur = trial
        else:
            if ch.isascii() and ch.isalnum() and " " in cur:
                head, _, tail = cur.rpartition(" ")
                lines.append(head)
                cur = tail + ch
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines


def draw_text(d, xy, s, size, color=TEXT, weight="regular", anchor="la", spacing=1.35):
    x, y = xy
    lines = wrap(s, size, CONTENT_W, weight) if "\n" not in s else s.split("\n")
    lh = int(size * spacing)
    for i, ln in enumerate(lines):
        d.text((x, y + i * lh), ln, font=font(size, weight), fill=color, anchor=anchor)
    return len(lines) * lh


def rrect(d, box, r=6, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


# ---------------------------------------------------------------- 自动动效表
def auto_motion(sc):
    """默认入场时间。若 spec 给了 beats（按台词分句算出的时刻），就把元素挂到 beats 上，
    让画面跟着台词走——这是"不出现长于 1.2 秒死区"的关键。"""
    form = sc.get("form")
    beats = sc.get("beats") or []
    m = []
    seq = []            # 按顺序要出场的元素

    if form == "bignum":
        seq = ["title", "number", "caption", "note"]
    elif form == "chart":
        seq = ["title", "chart"]
    elif form == "list":
        seq = ["title"] + [f"items[{i}]" for i in range(len((sc.get("slots") or {}).get("items", [])))]
    elif form == "relation":
        seq = ["title", "center"] + [f"satellites[{i}]"
                                     for i in range(len((sc.get("slots") or {}).get("satellites", [])))]
    elif form == "photo":
        seq = ["image", "title", "caption"]
    elif form == "sources":
        seq = ["closing", "blocks"]
    elif form == "evidence":
        seq = ["title", "image", "attrib"]
    elif form == "timeline":
        seq = ["title"] + [f"points[{i}]"
                           for i in range(len((sc.get("slots") or {}).get("points", [])))]
    else:
        seq = ["title"]

    if beats:
        for i, item in enumerate(seq):
            at = beats[i] if i < len(beats) else beats[-1] + (i - len(beats) + 1) * 0.6
            m.append({"item": item, "at": max(0.0, float(at)), "dur": 0.42, "ease": "out"})
        m.insert(0, {"item": "chapter", "at": 0.0, "dur": 0.30, "ease": "out"})
        return m

    m = [{"item": "chapter", "at": 0.0, "dur": 0.30, "ease": "out"},
         {"item": "title", "at": 0.12, "dur": 0.42, "ease": "out"}]
    if form == "bignum":
        m += [{"item": "number", "at": 0.30, "dur": 0.75, "ease": "out"},
              {"item": "caption", "at": 1.05, "dur": 0.40, "ease": "out"},
              {"item": "note", "at": 1.45, "dur": 0.30, "ease": "out"}]
    elif form == "chart":
        m += [{"item": "chart", "at": 0.35, "dur": 0.80, "ease": "out"}]
    elif form == "list":
        for i in range(len((sc.get("slots") or {}).get("items", []))):
            m.append({"item": f"items[{i}]", "at": 0.45 + i * 0.55, "dur": 0.42, "ease": "out"})
    elif form == "relation":
        m += [{"item": "center", "at": 0.35, "dur": 0.40, "ease": "out"}]
        for i in range(len((sc.get("slots") or {}).get("satellites", []))):
            m.append({"item": f"satellites[{i}]", "at": 0.75 + i * 0.50, "dur": 0.42, "ease": "out"})
    elif form == "photo":
        m += [{"item": "image", "at": 0.0, "dur": 0.90, "ease": "out"},
              {"item": "caption", "at": 0.55, "dur": 0.45, "ease": "out"}]
    elif form == "sources":
        m += [{"item": "closing", "at": 0.15, "dur": 0.55, "ease": "out"},
              {"item": "blocks", "at": 0.60, "dur": 0.70, "ease": "out"}]
    elif form == "evidence":
        m += [{"item": "image", "at": 0.15, "dur": 0.60, "ease": "out"},
              {"item": "attrib", "at": 0.80, "dur": 0.35, "ease": "out"}]
    elif form == "timeline":
        for i in range(len((sc.get("slots") or {}).get("points", []))):
            m.append({"item": f"points[{i}]", "at": 0.40 + i * 0.55, "dur": 0.42, "ease": "out"})
    return m


def motion_map(sc):
    """item -> (start, dur, ease)"""
    mm = {}
    for e in sc.get("motion") or auto_motion(sc):
        mm[e["item"]] = (float(e.get("at", 0)), float(e.get("dur", 0.4)), e.get("ease", "out"))
    return mm


def P(mm, item, t, default=1.0):
    if item not in mm:
        return default
    st, du, ease = mm[item]
    return prog(t, st, du, ease)


# ---------------------------------------------------------------- chrome
def draw_chrome(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    # 常驻页眉：左上账号标签 / 右上标的标签（参考片的核心识别元素）
    if sc.get("label_left"):
        d.text((58, 34), sc["label_left"], font=font(22, "bold"), fill="#B9BEC4", anchor="la")
        d.line([(58, 66), (58 + int(240 * ease_out(P(mm, "chapter", t, 1.0))), 66)],
               fill=ACCENT, width=2)
    if sc.get("label_right"):
        d.text((W - 58, 36), sc["label_right"], font=font(30, "bold"), fill="#E8E8E8", anchor="ra")
    chapter = sc.get("chapter")
    if chapter:
        p = P(mm, "chapter", t)
        y = lift(96, p, 18)
        head, sep, tail = chapter.partition("·")
        if sep:
            d.text((MARGIN, y), head, font=font(60, "bold"), fill=blend(TEXT, p), anchor="la")
            dx = text_w(head, 60, "bold")
            d.text((MARGIN + dx, y), "·", font=font(60, "bold"), fill=blend(ACCENT, p), anchor="la")
            d.text((MARGIN + dx + text_w("·", 60, "bold"), y), tail,
                   font=font(60, "bold"), fill=blend(TEXT, p), anchor="la")
        else:
            d.text((MARGIN, y), chapter, font=font(60, "bold"), fill=blend(TEXT, p), anchor="la")
        if sc.get("brand"):
            d.text((RIGHT, 106), sc["brand"], font=font(34), fill=blend(MUTED, p), anchor="ra")

    if sc.get("when"):
        p = P(mm, "chapter", t)
        d.text((MARGIN, lift(176, p, 16)), sc["when"], font=font(40),
               fill=blend(TEXT, p), anchor="la")
    if sc.get("rel"):
        p = P(mm, "chapter", t, 1.0)
        d.text((MARGIN, 248), sc["rel"], font=font(30), fill=blend(MUTED, p * 0.95), anchor="la")

    # 底部字幕带
    ps = P(mm, "subtitle", t, 1.0 if sc.get("subtitle") else 0.0)
    if sc.get("subtitle") and ps > 0:
        lines = wrap(sc["subtitle"], 54, CONTENT_W - 80)[:2]
        y0 = 1000 - int(54 * 1.35) * (len(lines) - 1)
        for i, ln in enumerate(lines):
            d.text((MARGIN, y0 + i * int(54 * 1.35)), ln, font=font(54),
                   fill=blend(TEXT, ps), anchor="ls")
        if len(lines) == 1 and sc.get("disclaimer", True):
            d.text((MARGIN, 1012), "本视频引用的研究与数据均标注出处",
                   font=font(20), fill=blend(DIM, ps), anchor="la")

    if sc.get("source"):
        p = P(mm, "source", t, 1.0)
        draw_text(d, (MARGIN, 884), sc["source"], 21, blend(DIM, p))
    tc = sc.get("tc") if sc.get("show_tc") else None
    if tc:
        p = P(mm, "tc", t, 1.0)
        d.text((RIGHT - 40, 1006), f"TC {tc}", font=font(19, "mono"), fill=blend(DIM, p), anchor="ra")
    elif sc.get("disclaimer", True) and not sc.get("subtitle"):
        d.text((MARGIN, 1012), "本视频引用的研究与数据均标注出处",
               font=font(20), fill=blend(DIM, P(mm, "tc", t)), anchor="la")


def draw_kicker_block(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    title = sc.get("title")
    if not title:
        return
    p = ease_out(P(mm, "title", t))
    y = lift(310, p, 18)
    for ln in wrap(title, 64, float(sc.get("title_w", 900)))[:2]:
        reveal_text(img, (MARGIN, y + 64), ln, 64, TEXT, p, weight="bold")
        y += int(64 * 1.3)
    y += 12
    if sc.get("kicker"):
        pk = P(mm, "kicker", t, p)
        d.text((MARGIN, y), sc["kicker"], font=font(28), fill=blend(MUTED, pk), anchor="la")


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


_IMG_CACHE = {}


def _load(path):
    im = _IMG_CACHE.get(path)
    if im is None:
        im = Image.open(path).convert("RGB")
        _IMG_CACHE[path] = im
    return im


def _paste(path, box):
    x0, y0, x1, y1 = [int(v) for v in box]
    bw, bh = x1 - x0, y1 - y0
    im = _load(path)
    scale = max(bw / im.width, bh / im.height)
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    left, top = (im.width - bw) // 2, (im.height - bh) // 2
    return im.crop((left, top, left + bw, top + bh))


def _fade_img(img, box, src, p, drift=0.0, soften=0):
    """图片淡入 + 轻微推进（1.06→1.00），静止时也有呼吸感。"""
    if p <= 0.001:
        return
    zoom = 1.06 - 0.06 * p
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    tw, th = int(bw * zoom), int(bh * zoom)
    tile = _paste(src, (0, 0, tw, th))
    left = (tile.width - bw) // 2 + int(drift * (1 - p))
    top = (tile.height - bh) // 2
    left = max(0, min(tile.width - bw, left))
    tile = tile.crop((left, top, left + bw, top + bh))
    if soften > 0:
        k = max(10, int(soften * 3))
        tile = tile.resize((max(8, bw // k), max(8, bh // k)), Image.BILINEAR).resize(
            (bw, bh), Image.BICUBIC).filter(ImageFilter.GaussianBlur(soften / 2))
    if p < 0.999:
        tile = Image.blend(Image.new("RGB", tile.size, _rgb(BG)), tile, p)
    img.paste(tile, (x0, y0))


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
        draw_text(d, (960, 780), s["quote"], 36, blend(TEXT, p))
    if s.get("attrib"):
        pa = P(mm, "attrib", t, p)
        d.text((960, lift(826, pa, 10)), s["attrib"], font=font(22), fill=blend(DIM, pa), anchor="la")


def form_photo(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    s = sc.get("slots", {})
    src = s.get("image")
    p = P(mm, "image", t)
    if sc.get("depth") in ("bg", "split"):
        if s.get("caption"):
            pc = P(mm, "caption", t)
            draw_text(d, (MARGIN, lift(640, pc, 12)), s["caption"], 30, blend(MUTED, pc))
        if s.get("credit"):
            d.text((900, 818), s["credit"], font=font(20), fill=blend(DIM, p), anchor="la")
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
            draw_text(d, (MARGIN, lift(640, pc, 12)), s["caption"], 30, blend(MUTED, pc))
        if s.get("credit"):
            d.text((900, 818), s["credit"], font=font(20), fill=blend(DIM, p), anchor="la")
        return

    if src and os.path.exists(src):
        _fade_img(img, (0, 0, W, H), src, p)
    else:
        _placeholder(img, (0, 0, W, H), "整幅图片位", p)
    if p < 0.999:
        scrim = Image.new("RGB", (W, H), _rgb(BG))
        img.paste(Image.blend(scrim, img.convert("RGB"), p), (0, 0))
    d = ImageDraw.Draw(img)
    band_w = int(W * (s.get("scrim", 0.46)))
    overlay = Image.new("RGBA", (W, band_w), (5, 6, 8, 200))
    img.paste(Image.alpha_composite(img.crop((0, 0, W, band_w)).convert("RGBA"), overlay).convert("RGB"),
              (0, 0))
    d = ImageDraw.Draw(img)
    if s.get("caption"):
        pc = P(mm, "caption", t)
        draw_text(d, (MARGIN, 700), s["caption"], 32, blend(TEXT, pc))
    if s.get("credit"):
        d.text((MARGIN, 840), s["credit"], font=font(20), fill=blend(MUTED, p), anchor="la")


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
        reveal_text(img, (236 + dx, yy + 32), it.get("text", ""), 32, TEXT, pe)
        y += 84
    if s.get("media") and os.path.exists(s["media"]):
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
    for j, block in enumerate(s.get("blocks", [])):
        pj = clamp((pb - j * 0.12) / 0.88) if pb < 1 else 1.0
        if pj <= 0:
            continue
        if block.get("title"):
            d.text((1226, y), block["title"], font=font(24, "bold"), fill=blend(MUTED, pj), anchor="la")
            y += 44
        for line in block.get("lines", []):
            for k, ln in enumerate(wrap(line, 21, 540)[:2]):
                pl = clamp(pj * 1.3 - k * 0.1)
                d.text((1226 + 12 * (1 - pl), y), ln, font=font(21), fill=blend(DIM, pl), anchor="la")
                y += 34
        y += 16


FORMS = {
    "bignum": form_bignum, "evidence": form_evidence, "list": form_list,
    "timeline": form_timeline, "relation": form_relation, "sources": form_sources,
    "photo": form_photo, "chart": form_chart,
}


def draw_strap(img, sc, t, mm):
    """底部一句话：直接画在左栏/暗底上，不铺横贯色带——色带会切断画面主体。"""
    strap = sc.get("strap")
    if not strap:
        return
    p = ease_out(P(mm, "strap", t, 1.0))
    d = ImageDraw.Draw(img)
    y = 812
    x = MARGIN
    tab = sc.get("strap_tab") or ""
    if tab:
        tw = int(text_w(tab, 22, "bold")) + 28
        d.rectangle((x, y - 16, x + tw, y + 16), fill=blend(ACCENT, p))
        d.text((x + 14, y), tab, font=font(22, "bold"), fill=blend("#FFFFFF", p), anchor="lm")
        x += tw + 18
    limit = int(W * 0.62) - x if sc.get("depth") == "split" else 1500 - x
    text = strap
    while text_w(text, 34, "bold") > limit and len(text) > 6:
        text = text[:-2]
    d.text((x, y), text, font=font(34, "bold"), fill=blend(TEXT, p), anchor="lm")
    clock = sc.get("clock")
    if clock:
        d.text((RIGHT, y), str(clock), font=font(20, "mono"), fill=blend(DIM, p), anchor="rm")


def draw_callouts(img, sc, t, mm):
    """证据标注：细引线 + 小标签，线先长出来，标签再出现。"""
    calls = sc.get("callouts") or []
    d = ImageDraw.Draw(img)
    for i, c in enumerate(calls):
        p = ease_out(P(mm, f"callout[{i}]", t, 0.0))
        if p <= 0.001:
            continue
        x, y = int(c.get("x", 0.5) * W), int(c.get("y", 0.5) * H)
        tx, ty = x + int(c.get("dx", 120) * p), y + int(c.get("dy", -80) * p)
        d.line([(x, y), (tx, ty), (tx + 26, ty)], fill=blend("#E8E8E8", p), width=2)
        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=blend(ACCENT, p))
        if p > 0.55:
            d.text((tx + 34, ty), c.get("text", ""), font=font(24, "bold"),
                   fill=blend(TEXT, clamp((p - 0.55) / 0.45)), anchor="lm")


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


# ---------------------------------------------------------------- 输出
def spec_duration(spec):
    return sum(float(s.get("dur", 4)) for s in spec["scenes"])


def _ffmpeg():
    return shutil.which("ffmpeg")


def resolve_media(spec_dir, scenes):
    for sc in scenes:
        for k in ("bg", "sound", "media2"):
            v = sc.get(k)
            if isinstance(v, str) and v and not os.path.isabs(v):
                sc[k] = os.path.normpath(os.path.join(spec_dir, v))
        slots = sc.get("slots") or {}
        for k in ("image", "media", "left", "right"):
            v = slots.get(k)
            if isinstance(v, str) and v and not os.path.isabs(v):
                slots[k] = os.path.normpath(os.path.join(spec_dir, v))


def render_segment(sc, path, fps=FPS, brand=None):
    """渲染一段带动效的 mp4（无音轨）。"""
    dur = float(sc.get("dur", 4))
    n = max(2, int(round(dur * fps)))
    w, h = W, H
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(n):
            frame = render_scene(sc, t=i / fps, spec_brand=brand)
            p.stdin.write(frame.tobytes())
    finally:
        p.stdin.close()
        err = p.stderr.read().decode("utf-8", "ignore")
        p.wait()
    if p.returncode != 0:
        print(err[-1200:])
        raise SystemExit(f"渲染 {sc.get('id')} 失败")


# 转场在 render_film 里逐帧合成。v2 的 concat_with_transitions（ffmpeg xfade 链）已删除：
# 每接一次 xfade 就会吃掉一个转场时长的总长（每镜 −trans_dur），口播片会整片音画错位；
# 且某镜 dur 小于转场时长时 ffmpeg 直接报错。现在整片时长严格等于 sum(dur)。


def apply_camera(img, t, dur, amt=0.012):
    """极缓推镜：整幅 1.000→1.025，让静止段也不是完全死帧。

    只走 scene 级 `camera` 字段，**默认 0（关）**——排版文字层不做缩放推拉，
    要开就写 `"camera": 0.010~0.012`，只给成片级微推用。
    """
    if amt <= 0:
        return img
    p = clamp(t / max(0.1, dur))
    z = 1 + amt * p
    w2, h2 = int(W * z), int(H * z)
    im = img.resize((w2, h2), Image.BILINEAR)
    left = int((w2 - W) * 0.5)
    top = int((h2 - H) * 0.5)
    return im.crop((left, top, left + W, top + H))


def render_film(spec, out_path, fps=FPS, brand=None, on_progress=None):
    """整片渲染：转场在渲染器内部完成（黑场 / 叠化 / 划像），一次编码，
    不依赖 ffmpeg 的 xfade 链，时间轴完全可控。

    转场吃掉的是前一镜的**尾部**画面（转场期间两镜同时可见），
    所以输出总时长 = sum(dur)，不会像 xfade 那样每接一次就短一段。
    """
    scenes = spec["scenes"]
    starts, t = [], 0.0
    for sc in scenes:
        starts.append(t)
        t += float(sc["dur"])
    total = t

    W_, H_ = W, H
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W_}x{H_}", "-r", str(fps), "-i", "-",
           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n = int(round(total * fps))
    black = Image.new("RGB", (W_, H_), (0, 0, 0))
    try:
        for i in range(n):
            T = i / fps
            j = next((jj for jj, s in enumerate(starts) if T < s), len(scenes))
            idx = max(0, min(len(scenes) - 1, j - 1))
            sc = scenes[idx]
            tr = sc.get("transition") or {}
            kind, xd = tr.get("type", "cut"), float(tr.get("duration", 0) or 0)
            end = starts[idx] + float(sc["dur"])
            frame = render_scene(sc, t=T - starts[idx], spec_brand=brand)
            frame = apply_camera(frame, T - starts[idx], float(sc["dur"]),
                                 float(sc.get("camera", 0.0)))
            if kind in ("cut", None, "") or xd <= 0 or idx + 1 >= len(scenes):
                pass
            elif T > end - xd:
                p2 = clamp((T - (end - xd)) / xd)
                nxt = scenes[idx + 1]
                nt = max(0.0, T - starts[idx + 1] + 0.001)
                b = render_scene(nxt, t=nt, spec_brand=brand)
                b = apply_camera(b, nt, float(nxt["dur"]), float(nxt.get("camera", 0.0)))
                if kind == "dissolve":
                    frame = Image.blend(frame, b, p2)
                elif kind in ("fade", "blur"):
                    if p2 < 0.5:
                        frame = Image.blend(frame, black, p2 * 2)
                    else:
                        frame = Image.blend(black, b, (p2 - 0.5) * 2)
                elif kind == "wipe":
                    cut = int(W_ * p2)
                    frame = frame.copy()
                    if cut > 0:
                        frame.paste(b.crop((0, 0, cut, H_)), (0, 0))
            p.stdin.write(frame.tobytes())
            if on_progress and i % 120 == 0:
                on_progress(i / n)
    finally:
        p.stdin.close()
        err = p.stderr.read().decode("utf-8", "ignore")
        p.wait()
    if p.returncode != 0:
        print(err[-1500:])
        raise SystemExit("整片渲染失败")
    return out_path


def contact_sheet(spec, path, cols=4, thumb_w=480):
    scenes = spec["scenes"]
    rows = (len(scenes) + cols - 1) // cols
    th = int(thumb_w * H / W)
    sheet = Image.new("RGB", (cols * thumb_w, rows * th), "#000000")
    for i, sc in enumerate(scenes):
        im = render_scene(sc, spec_brand=spec.get("brand")).resize((thumb_w, th), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * thumb_w, (i // cols) * th))
    sheet.save(path)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    spec_path, out_dir = argv[1], argv[2]
    spec = json.load(open(spec_path, encoding="utf-8-sig"))   # 兼容 Windows 记事本的 BOM
    resolve_media(os.path.dirname(os.path.abspath(spec_path)), spec["scenes"])
    os.makedirs(out_dir, exist_ok=True)
    flags = set(a for a in argv[3:] if a.startswith("--"))
    if not flags:
        flags = {"--png"}
    brand = spec.get("brand")

    if "--png" in flags:
        for sc in spec["scenes"]:
            render_scene(sc, spec_brand=brand).save(os.path.join(out_dir, f"{sc['id']}.png"))
        print(f"渲染 {len(spec['scenes'])} 张终帧 -> {out_dir}")
    if "--contact" in flags or "--floorplan" in flags:      # --floorplan 是 v2 文档里的旧名
        contact_sheet(spec, os.path.join(out_dir, "contact.png"))
        print(f"拼图 -> {os.path.join(out_dir, 'contact.png')}")

    fps = None
    if "--mp4" in flags or "--video" in flags:
        if not _ffmpeg():
            raise SystemExit("需要 ffmpeg（出 mp4）")
        # fps 以 spec 的 canvas.fps 为准（2026-11 案例回灌：横版交 30，
        # 别再让 spec 写了 30 而渲染偷偷用 24）
        canvas_fps = (spec.get("canvas") or {}).get("fps")
        if canvas_fps is None:
            print(f"提示：canvas.fps 未写，按 {FPS}fps 渲染；横版默认建议 30")
        fps = int(canvas_fps or FPS)
    if "--mp4" in flags:
        segdir = os.path.join(out_dir, "segs")
        os.makedirs(segdir, exist_ok=True)
        for sc in spec["scenes"]:
            render_segment(sc, os.path.join(segdir, f"{sc['id']}.mp4"), fps=fps, brand=brand)
        print(f"渲染 {len(spec['scenes'])} 段（无转场）-> {segdir}")
    if "--video" in flags:
        i = argv.index("--video")
        target = argv[i + 1] if len(argv) > i + 1 else os.path.join(out_dir, "video.mp4")
        if target.startswith("--"):
            target = os.path.join(out_dir, "video.mp4")
        parent = os.path.dirname(os.path.abspath(target))
        os.makedirs(parent, exist_ok=True)
        render_film(spec, target, fps=fps, brand=brand)
        print(f"整片 -> {target}  （时长 {spec_duration(spec):.1f}s，转场在片内合成）")
    print(f"总时长 {spec_duration(spec):.1f}s / {len(spec['scenes'])} 镜")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
