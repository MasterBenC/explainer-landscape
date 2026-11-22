"""chrome 模板层：常驻页眉、章节牌、字幕带、来源行/时间码、kicker 标题块、
下三分之一横条（strap）、证据标注（callouts）。全是"写了就画"的可选字段。"""
from __future__ import annotations

from PIL import ImageDraw

from kit_common import (
    ACCENT, CONTENT_W, DIM, H, LINE, MARGIN, MUTED, P, RIGHT, TEXT, W,
    blend, clamp, draw_text, ease_out, fit_text, font, lift, reveal_text, text_w,
    warn_once, wrap,
)


# ---------------------------------------------------------------- 字幕容量
SUB_SIZE = 54                 # 字幕字号
SUB_W = CONTENT_W - 80        # 可用宽 1572px
SUB_LINES = 2                 # 最多两行
SUB_LH = int(SUB_SIZE * 1.35)  # 行高 72

# 免责声明文案只有这一份（老版在两处分支里各写了一遍，改一处漏一处）
DISCLAIMER = "本视频引用的研究与数据均标注出处"


def subtitle_capacity() -> int:
    """一行字幕大约能放几个汉字：1572 / 54 ≈ 29。audit.py 用同一个数报阈值。"""
    return int(SUB_W // SUB_SIZE)


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
        all_lines = wrap(sc["subtitle"], SUB_SIZE, SUB_W)
        lines = all_lines[:SUB_LINES]
        # 超出两行以前是静默截掉，成片里字幕说半句没人知道——现在至少喊一声。
        if len(all_lines) > SUB_LINES:
            warn_once(f"subtitle:{sc.get('id')}",
                      f"{sc.get('id')}: subtitle 折了 {len(all_lines)} 行，只画前 {SUB_LINES} 行"
                      f"（每行约 {subtitle_capacity()} 个汉字，超出部分被截断）")
        y0 = 1000 - SUB_LH * (len(lines) - 1)
        for i, ln in enumerate(lines):
            d.text((MARGIN, y0 + i * SUB_LH), ln, font=font(SUB_SIZE),
                   fill=blend(TEXT, ps), anchor="ls")
        if len(lines) == 1 and sc.get("disclaimer", True):
            d.text((MARGIN, 1012), DISCLAIMER,
                   font=font(20), fill=blend(DIM, ps), anchor="la")

    if sc.get("source"):
        p = P(mm, "source", t, 1.0)
        draw_text(d, (MARGIN, 884), sc["source"], 21, blend(DIM, p), max_w=CONTENT_W)
    tc = sc.get("tc") if sc.get("show_tc") else None
    if tc:
        p = P(mm, "tc", t, 1.0)
        d.text((RIGHT - 40, 1006), f"TC {tc}", font=font(19, "mono"), fill=blend(DIM, p), anchor="ra")
    elif sc.get("disclaimer", True) and not sc.get("subtitle"):
        d.text((MARGIN, 1012), DISCLAIMER,
               font=font(20), fill=blend(DIM, P(mm, "tc", t)), anchor="la")


def draw_kicker_block(img, sc, t, mm):
    d = ImageDraw.Draw(img)
    title = sc.get("title")
    if not title:
        return
    p = ease_out(P(mm, "title", t))
    y = lift(310, p, 18)
    title_w = float(sc.get("title_w", 900))
    tlines = wrap(title, 64, title_w)
    if len(tlines) > 2:
        warn_once(f"title:{sc.get('id')}",
                  f"{sc.get('id')}: title 折了 {len(tlines)} 行，只画前 2 行"
                  f"（title_w={int(title_w)}px / 64px），请缩短标题")
    for ln in tlines[:2]:
        reveal_text(img, (MARGIN, y + 64), ln, 64, TEXT, p, weight="bold")
        y += int(64 * 1.3)
    y += 12
    if sc.get("kicker"):
        pk = P(mm, "kicker", t, p)
        d.text((MARGIN, y), fit_text(sc["kicker"], 28, CONTENT_W),
               font=font(28), fill=blend(MUTED, pk), anchor="la")


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
    # 以前是逐字砍掉尾巴，成片里一句话缺最后一个字但没有任何提示；现在带省略号并提示一次。
    text = fit_text(strap, 34, max(120, limit), "bold")
    if text != strap:
        warn_once(f"strap:{sc.get('id')}",
                  f"{sc.get('id')}: strap 超出 {int(limit)}px 被截断为「{text}」，请拆成两镜")
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
            # 标注点靠右时标签会顶出画面右沿，按剩余宽度截断。
            lx = min(tx + 34, RIGHT - 120)
            d.text((lx, ty), fit_text(c.get("text", ""), 24, RIGHT - lx, "bold"),
                   font=font(24, "bold"), fill=blend(TEXT, clamp((p - 0.55) / 0.45)), anchor="lm")
