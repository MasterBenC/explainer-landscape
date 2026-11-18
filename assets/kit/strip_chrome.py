# -*- coding: utf-8 -*-
"""把 spec 的 chrome 切档：档案档 / 极简档 / 裸图档。

为什么要有这个脚本：`render.py` 的角标（日期戳、相对时间、来源行、时间码、品牌词）都是
可选字段，但 `disclaimer` 默认是 True——想彻底关掉就得逐场景改。2026-11 的实战里
用户最终选的是「极简档」：只留章节牌 + 字幕，来源收进片尾 sources 镜。

用法:
    python strip_chrome.py spec.json -o spec.minimal.json          # 极简档（保留 chapter）
    python strip_chrome.py spec.json -o spec.bare.json --drop-chapter
    python strip_chrome.py spec.json --check                       # 只报告每镜都有哪些 chrome

不动的字段：form / slots / motion / dur / id / title / kicker / depth / archival / callouts。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CHROME_KEYS = ("label_left", "label_right", "when", "rel", "source", "tc", "show_tc", "brand")


def strip(spec: dict, *, drop_chapter: bool) -> dict:
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
    noisy = [k for k in ("when", "rel", "source", "tc") if counts.get(k)]
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
    spec = json.loads(src.read_text(encoding="utf-8"))
    if a.check:
        return report(spec)
    if not a.out:
        ap.error("要么给 -o 输出文件，要么用 --check")

    out = Path(a.out)
    out.write_text(json.dumps(strip(spec, drop_chapter=a.drop_chapter),
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {out}  ({'裸图档' if a.drop_chapter else '极简档'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
