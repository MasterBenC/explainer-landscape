"""视频转场合成层：分镜片段（--mp4）、整片（--video，转场逐帧合成）、推镜、拼图、
spec 时长与媒体路径解析。"""
from __future__ import annotations

import os
import shutil
import subprocess

from PIL import Image

from kit_common import FPS, H, W, clamp
from kit_scene import render_scene


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
