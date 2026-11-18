#!/usr/bin/env python3
"""explainer-landscape 自检：把 spec.json 按模板规范过一遍，输出 FAIL / WARN。

用法：
    python audit.py spec.json            # 检查
    python audit.py spec.json --strict   # WARN 也算失败

退出码：0 全部通过或只有 WARN；1 有 FAIL。
"""
from __future__ import annotations

import json
import sys

MARGIN, RIGHT = 134, 1786
MAX_TITLE_W = 900          # 主标题可用宽（左栏）
FORMS = {"bignum", "evidence", "list", "timeline", "relation", "sources", "photo", "chart"}
REVEAL_LIMITS = {"items": 4, "points": 4, "satellites": 5, "data": 5}


def cjk_len(s: str) -> float:
    """粗估显示宽度：中文 1，英文 0.55。"""
    return sum(1.0 if ord(c) > 127 else 0.55 for c in s)


def check(spec: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    def fail(msg):
        out.append(("FAIL", msg))

    def warn(msg):
        out.append(("WARN", msg))

    scenes = spec.get("scenes", [])
    if not scenes:
        fail("spec 里没有 scenes")
        return out

    canvas = spec.get("canvas", {})
    if canvas and (canvas.get("w"), canvas.get("h")) != (1920, 1080):
        fail(f"画布必须是 1920×1080，当前 {canvas.get('w')}×{canvas.get('h')}")

    for i, sc in enumerate(scenes, 1):
        sid = sc.get("id", f"#{i}")
        form = sc.get("form")
        if form not in FORMS:
            fail(f"{sid}: 未知版式 {form!r}")
            continue
        dur = float(sc.get("dur", 0))
        if dur < 0.4:
            fail(f"{sid}: 时长 {dur}s 太短（最短 0.4s）")
        if dur > 25:
            warn(f"{sid}: 时长 {dur}s 偏长（实测最长 23.4s），确认里面有没有 4–6 个节拍")

        title = sc.get("title", "")
        if title and cjk_len(title) * 64 > MAX_TITLE_W * 2:
            fail(f"{sid}: 主标题太长（{cjk_len(title):.0f} 字宽），最多两行 14 字/行")
        if title and "\n" not in title and cjk_len(title) > 16:
            warn(f"{sid}: 主标题 {cjk_len(title):.0f} 字，考虑手动断行")

        sub = sc.get("subtitle", "")
        if sub and cjk_len(sub) > 44:
            warn(f"{sid}: 字幕 {cjk_len(sub):.0f} 字，超过单行容量（约 44 字），会折成两行并挤掉免责声明")

        chapter = sc.get("chapter")
        if chapter and not (sc.get("brand") or spec.get("brand")):
            # 极简档（spec["chrome"] 由 strip_chrome.py 打标）本来就不要品牌水印
            if spec.get("chrome") not in ("minimal", "bare"):
                warn(f"{sid}: 有章节牌但没有品牌水印（规范要求同时出现）")

        slots = sc.get("slots", {})
        for key, limit in REVEAL_LIMITS.items():
            arr = slots.get(key)
            if isinstance(arr, list) and len(arr) > limit:
                fail(f"{sid}: {key} 有 {len(arr)} 条，上限 {limit}")

        if form == "bignum":
            if not slots.get("number"):
                fail(f"{sid}: bignum 缺少 number")
            if not slots.get("caption"):
                warn(f"{sid}: bignum 没有 caption，观众记不住这个数字")
        if form == "evidence" and not slots.get("right"):
            warn(f"{sid}: evidence 右侧没有截图，可信度会掉")
        if form == "sources" and not slots.get("blocks"):
            fail(f"{sid}: sources 没有 blocks")

    # 节奏
    total = sum(float(s.get("dur", 0)) for s in scenes)
    if len(scenes) >= 8:
        spm = len(scenes) / total * 60
        if not 4 <= spm <= 14:
            warn(f"每分钟 {spm:.1f} 刀，数据叙事型区间是 4–8，混剪型是 8–14")
    durs = [float(s.get("dur", 0)) for s in scenes]
    if len(durs) >= 6:
        if all(2 <= d <= 5 for d in durs[:6]):
            warn("连续 6 镜都在 2–5s，节奏会平；插一镜 <2s 或 >10s")

    # 版式单调
    forms = [s.get("form") for s in scenes]
    run, prev = 0, None
    for f in forms:
        run = run + 1 if f == prev else 1
        prev = f
        if run >= 3:
            warn(f"连续 {run} 镜都是 {f}，换一种版式打断")
            break

    # 章节
    chapters = [s.get("chapter") for s in scenes if s.get("chapter")]
    uniq = []
    for c in chapters:
        if not uniq or uniq[-1] != c:
            uniq.append(c)
    if len(scenes) >= 12 and len(uniq) < 2:
        warn("只有一个章节，4 分钟片建议 3–5 个")

    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    spec = json.load(open(argv[1], encoding="utf-8"))
    strict = "--strict" in argv[2:]
    results = check(spec)
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
