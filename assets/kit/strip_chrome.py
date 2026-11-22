# -*- coding: utf-8 -*-
"""把 spec 的 chrome 切档：档案档 / 极简档 / 裸图档。

为什么要有这个脚本：`render.py` 的角标（日期戳、相对时间、来源行、时间码、品牌词）都是
可选字段，但 `disclaimer` 默认是 True——想彻底关掉就得逐场景改。2026-11 的实战里
用户最终选的是「极简档」：只留章节牌 + 字幕，来源收进片尾 sources 镜。

用法:
    python strip_chrome.py spec.json -o spec.minimal.json          # 极简档（保留 chapter）
    python strip_chrome.py spec.json -o spec.bare.json --drop-chapter
    python strip_chrome.py spec.json --check                       # 只报告每镜都有哪些 chrome

不动的字段：form / slots / motion / dur / id / title / subtitle / kicker / depth /
archival / callouts / transition / camera。`strap` / `strap_tab` / `clock` 属于 chrome
（下三分之一电视栏），切极简档时一起撤——否则屏幕上还横着一条横条。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CHROME_KEYS = ("label_left", "label_right", "when", "rel", "source", "tc", "show_tc",
               "brand", "strap", "strap_tab", "clock")


def collect_sources(spec: dict) -> list[str]:
    """把逐镜 `source` 按出现顺序去重收起来（切档前调用，撤之前先记住）。"""
    seen: list[str] = []
    for sc in spec.get("scenes", []):
        s = sc.get("source")
        if isinstance(s, str) and s.strip() and s.strip() not in seen:
            seen.append(s.strip())
    return seen


def merge_sources_into(spec: dict, dropped: list[str]) -> tuple[int, str]:
    """把被撤掉的逐镜来源并进片尾 sources 镜，返回 (新增条数, 人话状态)。

    以前切极简档是直接 `del sc["source"]`，字幕带干净了，但全片的出处也跟着消失——
    片尾来源页就成了半张假清单。现在默认并进去重汇总，并到哪一镜会明说。
    """
    if not dropped:
        return 0, "没有逐镜 source 要搬"
    idx = [i for i, sc in enumerate(spec.get("scenes", [])) if sc.get("form") == "sources"]
    if not idx:
        print("警告：撤掉了 %d 条逐镜 source，但 spec 里没有 form=\"sources\" 的片尾镜，"
              "这些出处无处安放，已丢弃：\n  - %s\n请手动补一个 sources 镜。"
              % (len(dropped), "\n  - ".join(dropped)), file=sys.stderr)
        return 0, "无片尾 sources 镜，来源已丢弃（见上方警告）"
    scenes = spec["scenes"]
    tgt = scenes[idx[-1]]
    slots = dict(tgt.get("slots") or {})
    blocks = [dict(b) for b in (slots.get("blocks") or [])]
    existing = "\n".join(ln for b in blocks for ln in (b.get("lines") or []))
    extra = [s for s in dropped if s not in existing]
    if not extra:
        return 0, "片尾 sources 已包含这些来源，无需追加"
    blocks.append({"title": "逐镜来源", "lines": extra})
    slots["blocks"] = blocks
    tgt["slots"] = slots
    return len(extra), f"来源已并入最后一镜 {tgt.get('id')}（新增 {len(extra)} 条）"


def strip(spec: dict, *, drop_chapter: bool) -> dict:
    dropped = collect_sources(spec)                           # 撤之前先记住
    out = {k: v for k, v in spec.items() if k != "brand"}      # spec 级 brand 也要撤
    scenes = []
    for sc in spec.get("scenes", []):
        sc = {k: v for k, v in sc.items() if k not in CHROME_KEYS}
        sc["disclaimer"] = False                              # 默认 True，必须显式关
        if drop_chapter:
            sc.pop("chapter", None)
        scenes.append(sc)
    out["scenes"] = scenes
    out["chrome"] = "bare" if drop_chapter else "minimal"      # 只是标记，渲染器不读
    n, note = merge_sources_into(out, dropped)
    if dropped:
        print(note, file=sys.stderr)
    return out


def report(spec: dict) -> int:
    scenes = spec.get("scenes", [])
    print(f"{len(scenes)} 镜；spec 级 brand = {spec.get('brand')!r}")
    counts: dict[str, int] = {}
    for sc in scenes:
        for k in CHROME_KEYS + ("chapter", "disclaimer"):
            if k in sc:
                counts[k] = counts.get(k, 0) + 1
    for k in CHROME_KEYS + ("chapter", "disclaimer"):
        n = counts.get(k, 0)
        flag = "✅" if n else "—"
        print(f"  {flag} {k:12s} {n}/{len(scenes)} 镜")
    noisy = [k for k in ("when", "rel", "source", "tc", "strap", "strap_tab", "clock")
             if counts.get(k)]
    if noisy:
        print(f"\n提示：{', '.join(noisy)} 还在 → 想走极简档就跑 "
              f"`python strip_chrome.py <spec> -o <out>`")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="spec chrome 切档")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out")
    ap.add_argument("--drop-chapter", action="store_true", help="连章节牌一起撤")
    ap.add_argument("--check", action="store_true", help="只报告，不写文件")
    a = ap.parse_args(argv[1:])

    src = Path(a.spec)
    spec = json.loads(src.read_text(encoding="utf-8-sig"))   # 与 render.py 一致，兼容 BOM
    if a.check:
        return report(spec)
    if not a.out:
        ap.error("要么给 -o 输出文件，要么用 --check")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(strip(spec, drop_chapter=a.drop_chapter),
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {out}  ({'裸图档' if a.drop_chapter else '极简档'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
