#!/usr/bin/env python3
"""explainer-landscape 渲染器 v3：spec.json -> 带动效的 16:9 画面。

每个元素都有入场时间。渲染函数接受场景内时间 t，输出该时刻的帧；
t 缺省时给最终状态（出静帧用）。

    python render.py spec.json out/ --png                 # 每镜终帧
    python render.py spec.json out/ --contact             # 拼图（旧名 --floorplan 仍可用）
    python render.py spec.json out/ --mp4                 # 每镜一段带动效的 mp4（剪辑用）
    python render.py spec.json out/ --video final.mp4     # 整片（转场在渲染器内合成）
    python render.py spec.json out/ --png --only s07,s12  # 只渲指定镜：改一镜不必重跑全片

`--video` 走 render_film：逐帧合成转场，**总时长严格等于各镜 dur 之和**，
不用 ffmpeg xfade，所以没有"每次转场吃掉一个转场时长"的问题，也不绑定 ffmpeg 版本。
`--mp4` 只出分镜片段（不含转场），留给剪辑软件自己拼。

字段全表见 references/spec-schema.md；动效语法见 references/motion-spec.md。
没有写 motion 的场景，按版式自动分配入场时间（章节牌 0s、标题 0.12s、主体 0.3s 起）。

本文件只是入口：解析 CLI、加载 spec、按选项调用各层。实现分在四个子模块里——

    kit_common.py   公共工具：设计 token、字体回退、动效缓动、文本排版、图片/底色缓存、档案化
    kit_chrome.py   chrome 模板：页眉 / 章节牌 / 字幕 / 来源行 / 时间码 / kicker / strap / callouts
    kit_forms.py    版式渲染器：八种 form + FORMS 注册表
    kit_scene.py    单镜合成：depth（bg / split / fg）+ 一帧的组装顺序
    kit_film.py     视频转场合成：--mp4 分镜片段、--video 整片、推镜、拼图

命令行、spec 格式、画面输出与拆分前完全一致（子模块都放在 assets/kit/，由本文件同目录导入，
所以 `python "<skill-dir>/assets/kit/render.py" spec.json out/ --png` 这种调用方式不用改）。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 允许从任意 cwd import 同目录兄弟模块

# 下面这批 import 同时也是对外再导出：`import render` 之后 render.render_scene /
# render.auto_motion / render.apply_camera 等旧用法继续可用。
from kit_common import (  # noqa: E402,F401
    ACCENT, BG, CARD, CONTENT_W, DIM, FPS, H, LINE, MARGIN, MUTED, RIGHT, TEXT, W,
    P, _rgb, archival, auto_motion, base_background, blend, clamp, count_value,
    draw_backdrop, draw_text, ease_in_out, ease_out, font, grain_tiles, lift,
    motion_map, prog, reveal_text, rrect, spring, text_w, wrap,
)
from kit_chrome import draw_callouts, draw_chrome, draw_kicker_block, draw_strap  # noqa: E402,F401
from kit_forms import (  # noqa: E402,F401
    FORMS, form_bignum, form_chart, form_evidence, form_list, form_photo,
    form_relation, form_sources, form_timeline,
)
from kit_film import (  # noqa: E402,F401
    _ffmpeg, apply_camera, contact_sheet, render_film, render_segment,
    resolve_media, spec_duration,
)
from kit_scene import render_scene  # noqa: E402,F401


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

    # --only s07,s12：只渲指定镜（改一镜不必重跑全片；未列出的镜不会写盘）
    only = None
    if "--only" in flags:
        i = argv.index("--only")
        if len(argv) > i + 1 and not argv[i + 1].startswith("--"):
            only = {s.strip() for s in argv[i + 1].split(",") if s.strip()}
        if not only:
            raise SystemExit("--only 后面要跟镜 id，逗号分隔，例如 --only s07,s12")
        missing = only - {sc["id"] for sc in spec["scenes"]}
        if missing:
            raise SystemExit(f"--only 里有不存在的镜 id：{sorted(missing)}")
    sel = [sc for sc in spec["scenes"] if only is None or sc["id"] in only]

    if "--png" in flags:
        for sc in sel:
            render_scene(sc, spec_brand=brand).save(os.path.join(out_dir, f"{sc['id']}.png"))
        print(f"渲染 {len(sel)} 张终帧 -> {out_dir}" + (f"（--only {','.join(sorted(only))}）" if only else ""))
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
        for sc in sel:
            render_segment(sc, os.path.join(segdir, f"{sc['id']}.mp4"), fps=fps, brand=brand)
        print(f"渲染 {len(sel)} 段（无转场）-> {segdir}" + (f"（--only {','.join(sorted(only))}）" if only else ""))
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
