#!/usr/bin/env python3
"""explainer-landscape 自检：把 spec.json 按模板规范过一遍，输出 FAIL / WARN。

用法：
    python audit.py spec.json                  # 结构与字段检查
    python audit.py spec.json --strict         # WARN 也算失败
    python audit.py spec.json --images out/    # 追加像素检查（红占比 / 填充率 / 亮度）

退出码：0 全部通过或只有 WARN；1 有 FAIL。

为什么检查这么细：`motion` 的键名写错、`ease` 值写错、`item` 拼错都**不会报错**，
只会静默绑空、动效不出现；`disclaimer` 不写默认 true，极简档会凭空多一行免责。
这些坑靠人眼看不出来，所以都做成机器可查项。
"""
from __future__ import annotations

import json
import os
import re
import sys

MARGIN, RIGHT = 134, 1786
MAX_TITLE_W = 900          # 主标题可用宽（左栏）
FORMS = {"bignum", "evidence", "list", "timeline", "relation", "sources", "photo", "chart"}
REVEAL_LIMITS = {"items": 4, "points": 4, "satellites": 5, "data": 5}
EASES = {"out", "in_out", "instant", "linear"}
EASE_ALIASES = {"ease_out", "ease_in_out", "ease_in"}     # 写了会静默变 linear
TRANSITIONS = {"cut", "fade", "dissolve", "wipe", "blur"}
FPS_OK = {24, 25, 30, 50, 60}
MINIMAL = {"minimal", "bare"}
# 不写 disclaimer 就等于 true，极简档必须显式 false
MINIMAL_RESIDUE = ("source", "when", "rel", "tc", "label_left", "label_right",
                   "brand", "strap", "strap_tab", "clock")

MOTION_COMMON = {"chapter", "title", "kicker", "subtitle", "source", "tc", "strap"}
MOTION_BY_FORM = {
    "bignum": {"number", "caption", "note"},
    "evidence": {"image", "attrib"},
    "list": {"items", "media"},
    "timeline": {"points", "delta"},
    "relation": {"center", "satellites"},
    "sources": {"closing", "blocks"},
    "chart": {"chart"},
    "photo": {"image", "caption"},
}
MOTION_INDEXED = {"items", "points", "satellites", "callout"}
# 数字自带单位也算数（"17年" "$2500万" "33 年"）
UNIT_HINT = re.compile(r"[年万亿%$￥€个家天月日秒倍元美刀]|美元|港元")


def cjk_len(s: str) -> float:
    """粗估显示宽度：中文 1，英文 0.55。"""
    return sum(1.0 if ord(c) > 127 else 0.55 for c in s)


def _exists(path: str, base_dir: str) -> bool:
    if not isinstance(path, str) or not path:
        return False
    return os.path.exists(path if os.path.isabs(path) else os.path.join(base_dir, path))


def _motion_checks(sc, sid, form, fail, warn) -> None:
    entries = sc.get("motion")
    if entries is None:
        return
    if not isinstance(entries, list):
        fail(f"{sid}: motion 必须是数组")
        return
    allowed = MOTION_COMMON | MOTION_BY_FORM.get(form, set())
    if sc.get("callouts"):
        allowed |= {"callout"}
    for k, e in enumerate(entries):
        tag = f"{sid}: motion[{k}]"
        if not isinstance(e, dict):
            fail(f"{tag} 不是对象")
            continue
        for bad in ("easing", "kind"):
            if bad in e:
                warn(f"{tag} 的 `{bad}` 渲染器不读（只认 item / at / dur / ease），"
                     f"照抄不会报错但也不会生效")
        item = e.get("item")
        if not item:
            fail(f"{tag} 缺 item")
            continue
        base = str(item).split("[")[0]
        if base not in allowed and base not in MOTION_INDEXED:
            fail(f"{tag} 的 item={item!r} 在这个版式里不存在（绑不上任何元素，静默失效）。"
                 f"{form} 可用：{', '.join(sorted(allowed))}")
        elif base not in allowed:
            warn(f"{tag} 的 item={item!r} 不属于 {form} 版式")
        ease = e.get("ease")
        if isinstance(ease, str):
            if ease in EASE_ALIASES:
                fail(f"{tag} 的 ease={ease!r} 不合法，会静默退化成 linear；"
                     f"写法是 out / in_out / instant / linear")
            elif ease not in EASES:
                warn(f"{tag} 的 ease={ease!r} 未定义，按 linear 处理")
        if "at" not in e:
            warn(f"{tag} 没写 at，默认 0")
        if "dur" not in e:
            warn(f"{tag} 没写 dur，默认 0.4")


def check(spec: dict, base_dir: str = ".") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    def fail(msg):
        out.append(("FAIL", msg))

    def warn(msg):
        out.append(("WARN", msg))

    scenes = spec.get("scenes", [])
    if not scenes:
        fail("spec 里没有 scenes")
        return out

    # ---- 画布 / fps
    canvas = spec.get("canvas", {})
    if canvas:
        if (canvas.get("w"), canvas.get("h")) != (1920, 1080):
            fail(f"画布必须是 1920×1080，当前 {canvas.get('w')}×{canvas.get('h')}")
        fps = canvas.get("fps")
        if fps is not None:
            try:
                fps_i = int(round(float(fps)))
            except (TypeError, ValueError):
                fail(f"canvas.fps={fps!r} 不是数字")
                fps_i = 0
            if fps_i and fps_i not in FPS_OK:
                fail(f"canvas.fps={fps} 不在 {{24,25,30,50,60}}；非标帧率会让平台二次转码抖动")
            elif fps_i and fps_i != 30:
                warn(f"canvas.fps={fps}：横版硬规则是 30fps 优先，只有素材本来就是该帧率时才用 {fps}")
    else:
        warn("没有 canvas 段：帧率会落到 30fps 兜底，建议显式写 canvas.fps")

    minimal = spec.get("chrome") in MINIMAL
    ids: set[str] = set()
    t_running = 0.0
    chapter_seen: list[str] = []

    for i, sc in enumerate(scenes, 1):
        sid = sc.get("id", f"#{i}")
        if sid in ids:
            fail(f"{sid}: id 重复（输出文件名会互相覆盖）")
        ids.add(sid)
        form = sc.get("form")
        if form not in FORMS:
            fail(f"{sid}: 未知版式 {form!r}")
            continue
        dur = float(sc.get("dur", 0))
        if dur < 0.4:
            fail(f"{sid}: 时长 {dur}s 太短（最短 0.4s）")
        if dur > 25:
            warn(f"{sid}: 时长 {dur}s 偏长（实测最长 23.4s），确认里面有没有 4–6 个节拍")

        # t 只是给人读的，但和累计时长对不上说明改过 dur 没改 t，时间轴会误导剪辑
        if "t" in sc:
            try:
                if abs(float(sc["t"]) - t_running) > 0.05:
                    warn(f"{sid}: t={sc['t']} 与前面 dur 累计 {t_running:.1f}s 不一致，"
                         f"改 dur 后记得同步 t")
            except (TypeError, ValueError):
                warn(f"{sid}: t={sc['t']!r} 不是数字")
        t_running += dur

        title = sc.get("title", "")
        if title and cjk_len(title) * 64 > MAX_TITLE_W * 2:
            fail(f"{sid}: 主标题太长（{cjk_len(title):.0f} 字宽），最多两行 14 字/行")
        if title and "\n" not in title and cjk_len(title) > 16:
            warn(f"{sid}: 主标题 {cjk_len(title):.0f} 字，考虑手动断行")

        sub = sc.get("subtitle", "")
        if sub and cjk_len(sub) > 44:
            warn(f"{sid}: 字幕 {cjk_len(sub):.0f} 字，超过单行容量（约 44 字），会折成两行并挤掉免责声明")

        chapter = sc.get("chapter")
        if chapter:
            chapter_seen.append(chapter)
            if not (sc.get("brand") or spec.get("brand")):
                # 极简档（spec["chrome"] 由 strip_chrome.py 打标）本来就不要品牌水印
                if not minimal:
                    warn(f"{sid}: 有章节牌但没有品牌水印（规范要求同时出现）")

        # ---- 转场
        tr = sc.get("transition")
        if tr is not None:
            if not isinstance(tr, dict):
                fail(f"{sid}: transition 必须是对象，如 {{'type': 'fade', 'duration': 0.5}}")
            else:
                kind = tr.get("type", "cut")
                xd = float(tr.get("duration", 0) or 0)
                if kind not in TRANSITIONS:
                    fail(f"{sid}: transition.type={kind!r} 不支持（{'/'.join(sorted(TRANSITIONS))}）")
                if kind != "cut" and xd <= 0:
                    fail(f"{sid}: transition.type={kind} 但 duration=0，转场不会发生")
                if xd >= dur:
                    fail(f"{sid}: transition.duration={xd}s ≥ 本镜 dur={dur}s，"
                         f"整镜都在转场里")
                elif kind != "cut" and xd > 0.8:
                    warn(f"{sid}: 转场 {xd}s 偏长（实测 0.35–0.6s）")

        # ---- 深度 / 背景 / 相机
        depth = sc.get("depth", "bg")
        if depth not in {"bg", "fg", "split"}:
            fail(f"{sid}: depth={depth!r} 不支持（bg / fg / split）")
        bg = sc.get("bg")
        if bg and not _exists(bg, base_dir):
            fail(f"{sid}: bg 指向的文件不存在：{bg}")
        if depth == "split" and not bg:
            fail(f"{sid}: depth=split 必须给 bg（左侧实色栏 + 右侧图）")
        cam = sc.get("camera")
        if cam is not None:
            try:
                cam = float(cam)
            except (TypeError, ValueError):
                fail(f"{sid}: camera={sc.get('camera')!r} 不是数字")
                cam = 0.0
            if cam > 0.02:
                fail(f"{sid}: camera={cam} 超过 0.012，重采样会抖（这是全幅微推，不是 Ken Burns）")
        if sc.get("clock") is not None and not sc.get("strap"):
            warn(f"{sid}: 写了 clock 但没有 strap，时间戳不会画（它挂在横条右端）")

        # ---- 极简档残留（y > 860 的 chrome）
        if minimal:
            for k in MINIMAL_RESIDUE:
                if k in sc:
                    warn(f"{sid}: 极简档不该有 `{k}`（它不是字幕带里的东西，"
                         f"会破坏「底部只有字幕」）")
            if sc.get("disclaimer", True):
                warn(f"{sid}: 极简档忘了 `\"disclaimer\": false`（默认 true，会画一行免责）")
        strap = sc.get("strap")
        if strap and cjk_len(strap) > 24:
            warn(f"{sid}: strap {cjk_len(strap):.0f} 字，横条一屏只写一个事实，超过会被硬截")

        # ---- 动效
        _motion_checks(sc, sid, form, fail, warn)

        # ---- 槽位
        slots = sc.get("slots", {})
        if not isinstance(slots, dict):
            fail(f"{sid}: slots 必须是对象")
            slots = {}
        for key, limit in REVEAL_LIMITS.items():
            arr = slots.get(key)
            if isinstance(arr, list) and len(arr) > limit:
                fail(f"{sid}: {key} 有 {len(arr)} 条，上限 {limit}")

        if form == "bignum":
            number = slots.get("number")
            unit = slots.get("unit")
            if not number:
                fail(f"{sid}: bignum 缺少 number")
            elif not unit and not UNIT_HINT.search(str(number)):
                fail(f"{sid}: bignum 的 number={number!r} 没有单位：写 `unit`，"
                     f"或把单位写进 number（17年 / $2500万）")
            elif not unit and UNIT_HINT.search(str(number)):
                warn(f"{sid}: 单位写在 number 里（{number!r}），拆到 `unit` 才能享受「小一号」排版")
            if not slots.get("caption") and not slots.get("note"):
                fail(f"{sid}: bignum 既没 caption 也没 note，观众记不住这个数字")
            elif not slots.get("caption"):
                warn(f"{sid}: bignum 没有 caption，只有数字没有解释")
        if form == "evidence":
            if not slots.get("right"):
                warn(f"{sid}: evidence 右侧没有截图，可信度会掉")
            elif not _exists(slots.get("right"), base_dir):
                fail(f"{sid}: evidence 右侧截图不存在：{slots.get('right')}")
            if slots.get("quote") and not slots.get("attrib"):
                fail(f"{sid}: evidence 有 quote 但没有 attrib（引文必须有机构·日期）")
        if form == "list":
            if not slots.get("items"):
                fail(f"{sid}: list 没有 items")
            if slots.get("media") and not _exists(slots.get("media"), base_dir):
                fail(f"{sid}: list 的 media 不存在：{slots.get('media')}")
        if form == "timeline":
            pts = slots.get("points") or []
            if len(pts) < 2:
                fail(f"{sid}: timeline 至少要 2 个点")
            if "axis" in slots:
                warn(f"{sid}: slots.axis 渲染器不读（只画 points 与 delta），别指望它出现")
        if form == "relation":
            sat = slots.get("satellites") or []
            if not slots.get("center"):
                fail(f"{sid}: relation 缺少 center")
            if not 3 <= len(sat) <= 5:
                warn(f"{sid}: relation 的 satellites 有 {len(sat)} 个，建议 3–5 个")
            if "note" in slots:
                warn(f"{sid}: relation 的 slots.note 渲染器不读"
                     f"（要注释就写场景级 strap 或 note）")
        if form == "sources":
            if not slots.get("blocks"):
                fail(f"{sid}: sources 没有 blocks")
            if not slots.get("closing"):
                warn(f"{sid}: sources 没有 closing 结语")
        if form == "chart":
            kind = slots.get("kind", "bar")
            data = slots.get("data") or []
            if kind not in {"bar", "line", "donut", "kpi"}:
                fail(f"{sid}: chart.kind={kind!r} 不支持（bar / line / donut / kpi）")
            if not data:
                fail(f"{sid}: chart 没有 data")
            if kind == "bar" and len(data) > 5:
                warn(f"{sid}: bar 有 {len(data)} 根，一屏最多 5 根")
            if kind == "line" and len(data) > 6:
                warn(f"{sid}: line 有 {len(data)} 个点，一屏最多 6 个")
            if kind == "donut" and len(data) > 5:
                warn(f"{sid}: donut 有 {len(data)} 段，一屏最多 5 段")
            if kind == "bar" and sum(1 for q in data if q.get("highlight")) > 1:
                fail(f"{sid}: bar 里 highlight 只能有一个（强调色全片 <2%）")
            if kind != "kpi":
                missing = [q.get("name") or q.get("label") for q in data
                           if q.get("value") in (None, "")]
                if missing:
                    fail(f"{sid}: chart 有 {len(missing)} 项没给 value")
        if form == "photo":
            # depth bg/fg/split 时图走场景级 `bg`，slots.image 只在整幅出血 / framed 卡片时才用
            img = slots.get("image") or (sc.get("bg") if depth in ("bg", "fg", "split") else None)
            if not img:
                fail(f"{sid}: photo 缺少 image（或 depth + bg）")
            elif not _exists(img, base_dir):
                fail(f"{sid}: photo 的图不存在：{img}")
            if slots.get("framed") and not slots.get("caption"):
                warn(f"{sid}: framed 卡片没有 caption")
            if not slots.get("credit"):
                warn(f"{sid}: photo 没有 credit（图必须能追到机构 + 日期，不许写「网络」）")

        # ---- callouts
        for k, c in enumerate(sc.get("callouts") or []):
            if not isinstance(c, dict):
                fail(f"{sid}: callouts[{k}] 不是对象")
                continue
            for axis in ("x", "y"):
                try:
                    v = float(c.get(axis, 0.5))
                except (TypeError, ValueError):
                    fail(f"{sid}: callouts[{k}].{axis} 不是数字")
                    continue
                if not 0.0 <= v <= 1.0:
                    fail(f"{sid}: callouts[{k}].{axis}={v} 必须是 0–1 的归一化坐标")
            if not c.get("text"):
                warn(f"{sid}: callouts[{k}] 没有 text")

    # ---- 结构：来源页必须是最后一镜
    src_idx = [i for i, s in enumerate(scenes) if s.get("form") == "sources"]
    if not src_idx:
        warn("没有 sources 镜：图源应集中到片尾来源页")
    else:
        if any(i != len(scenes) - 1 for i in src_idx):
            fail("sources 必须固定为最后一镜（现在它后面还有镜头），"
                 "否则「全部出处」的承诺是假的")
        if scenes[-1].get("form") != "sources":
            warn("最后一镜不是 sources：片尾没有来源清单")

    # ---- 节奏
    total = sum(float(s.get("dur", 0)) for s in scenes)
    if len(scenes) >= 8 and total > 0:
        spm = len(scenes) / total * 60
        if not 4 <= spm <= 14:
            warn(f"每分钟 {spm:.1f} 刀，数据叙事型区间是 4–8，混剪型是 8–14")
        elif spm < 8:
            warn(f"每分钟 {spm:.1f} 刀偏慢（实测基线 11 刀/分）：确认是不是有镜撑得太长")
    durs = [float(s.get("dur", 0)) for s in scenes]
    if len(durs) >= 6:
        if all(2 <= d <= 5 for d in durs[:6]):
            warn("连续 6 镜都在 2–5s，节奏会平；插一镜 <2s 或 >10s")

    # ---- 版式单调
    forms = [s.get("form") for s in scenes]
    run, prev = 0, None
    for f in forms:
        run = run + 1 if f == prev else 1
        prev = f
        if run >= 3:
            warn(f"连续 {run} 镜都是 {f}，换一种版式打断")
            break

    # ---- 章节
    uniq = []
    for c in chapter_seen:
        if not uniq or uniq[-1] != c:
            uniq.append(c)
    if len(scenes) >= 12 and len(uniq) < 2:
        warn("只有一个章节，4 分钟片建议 3–5 个")

    return out


def image_stats(path: str) -> tuple[float, float, float]:
    """返回 (填充率, 强调红占比, 平均亮度)。纯 PIL，不依赖 numpy。"""
    from PIL import Image
    im = Image.open(path).convert("RGB").resize((240, 135), Image.BILINEAR)
    rd, gd, bd = (ch.tobytes() for ch in im.split())
    n = max(1, len(rd))
    fill = red = 0
    bright = 0.0
    for i in range(n):
        r, g, b = rd[i], gd[i], bd[i]
        if r > 22 or g > 22 or b > 22:
            fill += 1
        if r > 140 and g < 90 and b < 80:
            red += 1
        bright += 0.299 * r + 0.587 * g + 0.114 * b
    return fill / n, red / n, bright / n


def check_images(spec: dict, img_dir: str, out: list[tuple[str, str]]) -> None:
    def fail(msg):
        out.append(("FAIL", msg))

    def warn(msg):
        out.append(("WARN", msg))

    for i, sc in enumerate(spec.get("scenes", []), 1):
        sid = sc.get("id", f"#{i}")
        path = os.path.join(img_dir, f"{sid}.png")
        if not os.path.exists(path):
            warn(f"{sid}: 没有渲染图 {path}，跳过像素检查")
            continue
        fill, red, bright = image_stats(path)
        depth = sc.get("depth", "bg")
        if red > 0.02:
            fail(f"{sid}: 强调红占 {red:.1%}，超过 2%（红色只给一个数字或一个分隔符）")
        slots = sc.get("slots") or {}
        framed = bool(slots.get("framed"))
        # 填充率 / 亮度只对"有图"的镜头有意义：纯排版镜本身就是近黑底 + 几行字。
        # 有 bg 走 bg/split/fg 阈值；没有 bg 的 photo 分「整幅出血」和「右侧卡片」两种。
        if sc.get("bg"):
            if depth == "fg" and not 0.20 <= fill <= 0.45:
                warn(f"{sid}: fg 镜填充率 {fill:.2f}，实测区间 0.31–0.34（0.20–0.45 可接受）")
            elif depth in ("bg", "split") and fill < 0.60:
                warn(f"{sid}: {depth} 镜填充率 {fill:.2f}，参考片 0.81–0.92——"
                     f"低于 0.6 观众会觉得「没做画面」")
        elif sc.get("form") == "photo" and slots.get("image"):
            if framed and not 0.20 <= fill <= 0.45:
                warn(f"{sid}: framed 卡片的填充率 {fill:.2f}，卡片应占画面 0.2–0.45")
            elif not framed and fill < 0.60:
                warn(f"{sid}: 整幅出血镜填充率 {fill:.2f}，低于 0.6 说明图没铺满")
        else:
            continue
        if bright < 30:
            warn(f"{sid}: 平均亮度 {bright:.0f}，低于 30 说明黑得太多（有图镜目标 50–90）")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    spec_path = argv[1]
    rest = argv[2:]
    strict = "--strict" in rest
    img_dir = None
    if "--images" in rest:
        k = rest.index("--images")
        img_dir = rest[k + 1] if len(rest) > k + 1 else None
    spec = json.load(open(spec_path, encoding="utf-8-sig"))   # 兼容 Windows 记事本的 BOM
    base_dir = os.path.dirname(os.path.abspath(spec_path))
    results = check(spec, base_dir)
    if img_dir:
        check_images(spec, img_dir, results)
    for level, msg in results:
        print(f"{level:4} {msg}")
    fails = sum(1 for lv, _ in results if lv == "FAIL")
    warns = sum(1 for lv, _ in results if lv == "WARN")
    total = sum(float(s.get("dur", 0)) for s in spec.get("scenes", []))
    print(f"\n{len(spec.get('scenes', []))} 镜 / {total:.1f}s / FAIL {fails} / WARN {warns}")
    if fails or (strict and warns):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
