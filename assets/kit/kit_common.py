"""公共工具层：设计 token、字体回退、动效与缓动、文本排版、图片/底色缓存、档案化。

被 kit_forms / kit_chrome / kit_scene / kit_film 引用。模块级缓存（字体、颗粒、底图、
图片）都只在这里定义，其他模块 import 的是**同一个 dict 对象**，所以拆分前后缓存
命中率不变，逐帧输出与拆分前一致。
"""
from __future__ import annotations

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


DEFAULT_DUR = 4.0  # 单镜 dur 缺省值，与 references/spec-schema.md 的「dur 默认 4s」一致


FONT_CANDIDATES = {
    # 顺序 = 优先级。各平台都把中文字体放在自己那一段里，跨平台一份表走完：
    #   Windows 微软雅黑 / 等线 / 黑体 · macOS 苹方 / 冬青 / 冬青黑 · Linux 各发行版 Noto CJK / 文泉驿
    "regular": [
        r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\Deng.ttf", r"C:\Windows\Fonts\simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        # Debian / Ubuntu：fonts-noto-cjk
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        # Fedora / RHEL：google-noto-cjk（也曾叫 google-noto-sans-cjk-fonts）
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-VF.otf.ttc",
        # Arch：noto-fonts-cjk
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-VF.otf.ttc",
        # openSUSE / 其他发行版的文泉驿
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc",
    ],
    "bold": [
        r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyhbd.ttf",
        r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\Dengb.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-VF.otf.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-VF.otf.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc",
    ],
    # 等宽只用来画时间码/编号，ASCII 就够，不要求 CJK 覆盖
    "mono": [
        r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\consolab.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ],
}


# spec 的 `fonts` 字段（{"regular": path, "bold": path, "mono": path}）由 render.py 在读完
# spec 后调 set_spec_fonts() 注册，优先级高于环境变量和平台候选路径。
FONT_ENV = {"regular": "EXPLAINER_FONT",
            "bold": "EXPLAINER_FONT_BOLD",
            "mono": "EXPLAINER_FONT_MONO"}

_spec_fonts: dict[str, str] = {}

_resolved: dict[str, str | None] = {}

_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def set_spec_fonts(fonts) -> None:
    """注册 spec 里的 `fonts` 字段（写相对路径也行，调用方负责改成绝对路径）。

    spec 换字体要立刻生效，所以顺手清掉已解析路径和字号缓存。
    """
    global _spec_fonts
    _spec_fonts = {k: str(v) for k, v in (fonts or {}).items()
                   if k in ("regular", "bold", "mono") and isinstance(v, str) and v}
    _resolved.clear()
    _cache.clear()


def _fc_lookup(pattern: str) -> str | None:
    """问 fontconfig 要一个字体文件路径（没有 fontconfig 就返回 None）。"""
    try:
        p = subprocess.run(["fc-match", "-f", "%{file}", pattern],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    out = (p.stdout or "").strip()
    return out if p.returncode == 0 and out and os.path.exists(out) else None


def _has_cjk(path: str) -> bool:
    """粗查这个字体到底有没有中文字形。

    fontconfig 不一定听话：`fc-match 'sans:lang=zh'` 在装了 Noto CJK 的机器上也可能给出
    一个纯拉丁字体，字体文件存在但中文全渲成 □。判据是「中」「文」两个字的掩码必须不同——
    缺字形时两者都是同一个 .notdef 方框（smoke_test.py 用同一招做豆腐块检测）。
    """
    try:
        f = ImageFont.truetype(path, 32)
        a, b = _glyph_pixels(f, "中"), _glyph_pixels(f, "文")
    except Exception:                                  # noqa: BLE001  字体坏了/读不了就当没有
        return False
    return bool(a.strip(b"\x00")) and a != b


def _glyph_pixels(f, ch: str) -> bytes:
    """把一个字画到 64×64 灰度画布上，返回像素字节。

    不能用 font.getmask(ch).tobytes()：ImagingCore 上没有 tobytes()（Pillow 13 实测），
    一调就 AttributeError，然后被上层当成「这字体没中文」全否掉。走 ImageDraw 最稳。
    """
    im = Image.new("L", (64, 64), 0)
    ImageDraw.Draw(im).text((0, 0), ch, font=f, fill=255)
    return im.tobytes()


def _resolve(weight: str) -> str | None:
    """按 spec fonts → 环境变量 → 平台候选路径 → fontconfig 兜底的顺序定一条路径。"""
    if weight in _resolved:
        return _resolved[weight]
    need_cjk = weight in ("regular", "bold")
    tries: list[str] = []

    def usable(path: str | None) -> bool:
        if not path:
            return False
        tries.append(path)
        if not os.path.exists(path):
            return False
        return _has_cjk(path) if need_cjk else True

    hit = None
    # 1) spec fonts 字段  2) 环境变量  3) 各平台候选路径
    cands = [_spec_fonts.get(weight), os.environ.get(FONT_ENV.get(weight, ""), "")]
    cands += list(FONT_CANDIDATES.get(weight, []))
    for c in cands:
        if usable(c):
            hit = c
            break
    # 4) fontconfig 兜底
    if hit is None and shutil.which("fc-match"):
        pattern = {"regular": "sans:lang=zh", "bold": "sans:bold:lang=zh",
                   "mono": "monospace"}[weight]
        for pat in (pattern, "sans-serif:lang=zh" if need_cjk else ""):
            if not pat:
                continue
            c = _fc_lookup(pat)
            if usable(c):
                hit = c
                break
    _resolved[weight] = hit
    if hit is None:
        _tried[f"__{weight}__"] = tries
    return hit


_tried: dict[str, list[str]] = {}


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key in _cache:
        return _cache[key]
    path = _resolve(weight)
    if path:
        f = ImageFont.truetype(path, size)
        _cache[key] = f
        return f
    # regular / bold 找不到任何中文字体时不能静默回退：load_default 没有 CJK 字形，
    # 会渲成 □□□ 且退出码仍是 0（2026-11 评审 C5，比报错更难查）。
    if weight in ("regular", "bold"):
        sys.stderr.write(
            "ERROR: 找不到可用的中文字体，中文会渲成方框。\n"
            "  试过（含 spec fonts / 环境变量 / 平台路径 / fc-match）：\n    "
            + "\n    ".join(_tried.get(f"__{weight}__", [])) + "\n"
            "  三种给法（优先级从高到低）：\n"
            '    1) spec 顶层写 "fonts": {"regular": "/path/xxx.ttc", "bold": "/path/xxx-bold.ttc"}\n'
            f"    2) 环境变量 {FONT_ENV[weight]}=/path/xxx.ttc\n"
            "    3) 装系统字体：Debian/Ubuntu `apt install fonts-noto-cjk`；"
            "Fedora `dnf install google-noto-cjk-fonts`；Arch `pacman -S noto-fonts-cjk`\n"
            "  macOS: 安装「苹方」（自带）；Windows: 确认 C:\\Windows\\Fonts\\msyh.ttc 存在\n")
        raise SystemExit(2)
    f = ImageFont.load_default(size)
    _cache[key] = f
    return f


def font_report() -> dict[str, str | None]:
    """每个字重最终解析到的字体文件（None = 没解析到，mono 会退到 Pillow 内置）。

    smoke_test.py 用它把「到底回退到了哪个字体」如实打出来。以前只查候选路径存不存在，
    会出现「路径在、字形没有」的假通过——DejaVu 就是这种：文件在，中文全是 □。
    """
    return {w: _resolve(w) for w in ("regular", "bold", "mono")}


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
    """预生成几张胶片颗粒图（n 张）。

    注意：调用方 archival() 按镜头 id 固定取其中一张（`tiles[seed % len(tiles)]`），
    缓存键也是镜 id，所以**颗粒是按镜静态的**，不随帧轮换、也没有门闪抖动——
    "档案感"来自这张固定颗粒图叠 2.2% 的透明度，不是逐帧噪点。
    """
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
    """档案化处理：去饱和 → 暖调 → 压暗角 → 叠一张按镜固定的颗粒（不逐帧轮换、无门闪）。"""
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
    # Pillow 带 raqm 时量"含换行的串"会直接抛 RuntimeError: raqm_layout() failed，
    # 所以按行拆开量、取最宽的一行（不含换行的串走同一路径，宽度与原实现完全一致）。
    if "\n" in s:
        return max((font(size, weight).getlength(ln) for ln in s.split("\n")), default=0.0)
    return font(size, weight).getlength(s)


def wrap(s: str, size: int, max_w: float, weight: str = "regular") -> list[str]:
    if not s:
        return []
    lines, cur = [], ""
    for ch in s:
        if ch == "\n":          # 显式换行 = 硬断行（与 draw_text 的 split("\n") 语义一致）
            lines.append(cur)
            cur = ""
            continue
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


def draw_text(d, xy, s, size, color=TEXT, weight="regular", anchor="la", spacing=1.35,
              max_w=None):
    """画一段（可折行的）文本，返回占用高度。

    max_w 是折行宽度，单位像素，**必须传真实栏宽**：双栏右栏、框内图说、分屏文字列
    的宽度都远小于整幅 CONTENT_W，不传就会横着越过栏线压到图上（2026-11 评审 P0-3）。
    缺省仍按整幅内容宽，保持全宽场景的老行为。
    """
    x, y = xy
    limit = CONTENT_W if max_w is None else float(max_w)
    lines = wrap(s, size, limit, weight) if "\n" not in s else s.split("\n")
    lh = int(size * spacing)
    for i, ln in enumerate(lines):
        d.text((x, y + i * lh), ln, font=font(size, weight), fill=color, anchor=anchor)
    return len(lines) * lh


def rrect(d, box, r=6, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


_WARNED: set[str] = set()


def warn_once(key: str, msg: str) -> None:
    """同一个问题只提醒一次。

    这些提示写在各版式的绘制函数里，而绘制函数每帧都会被调一次——不去重就是一帧一条
    刷满终端。key 用「问题 + 镜 id」，换一镜还会再提醒一次。
    """
    if key in _WARNED:
        return
    _WARNED.add(key)
    sys.stderr.write(f"WARN {msg}\n")


def fit_text(s: str, size: int, max_w: float, weight: str = "regular") -> str:
    """单行文本超宽就截尾加「…」。

    右对齐的署名、图源这类不折行的文本用它，宁可截断也不要越出栏线（P0-3）。
    """
    if not s or text_w(s, size, weight) <= max_w:
        return s
    cur = s
    while cur and text_w(cur + "…", size, weight) > max_w:
        cur = cur[:-1]
    return (cur + "…") if cur else ""


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
        return _with_callouts(sc, m)

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
    return _with_callouts(sc, m)


def _with_callouts(sc, m):
    """给已经有 callouts 的场景补默认入场（callout[i]）。

    以前 auto_motion 从不生成 callout 条目，而 kit_chrome.draw_callouts 读不到
    `callout[i]` 时进度缺省 0 → `if p <= 0.001: continue`，于是「按文档示例只写
    callouts、不写 motion」的标注一个都不出现（静默绑空）。已显式写了的条目不覆盖。
    """
    for i in range(len(sc.get("callouts") or [])):
        item = f"callout[{i}]"
        if any(e.get("item") == item for e in m if isinstance(e, dict)):
            continue
        m.append({"item": item, "at": 0.60 + i * 0.45, "dur": 0.50, "ease": "out"})
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
