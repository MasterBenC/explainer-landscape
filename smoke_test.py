#!/usr/bin/env python3
"""全链路冒烟测试：示例 spec -> 渲染 -> 自检 -> 去框，一条命令跑完，失败退出码非零。

    python smoke_test.py            # 默认：静帧 + audit + strip_chrome + 转场（有 ffmpeg 时）
    python smoke_test.py --no-video # 跳过转场/整片那步（没装 ffmpeg 或想更快）
    python smoke_test.py --keep     # 保留中间产物（默认跑完删临时目录）

只做"能不能跑通"的粗检：不比对像素、不做画质评审。要验版式和参数请跑
`assets/kit/audit.py`（含 `--images`）与 `references/qa-checklist.md`。

四步各查什么：
  1. 依赖：Pillow 能不能 import；出 mp4 的 ffmpeg 有没有（没有只影响转场那步）。
  2. 字体：微软雅黑 / 苹方 / Noto 谁在。缺前两个属正常（Linux 一般只有 Noto），
     **回退到哪个字体要报出来**；一个 CJK 字体都没有才算失败。
  3. 渲染 + 自检：assets/examples/ 两份示例 spec 各渲一遍静帧，再跑 audit.py
     （含 `--images` 像素检查）。
  4. 去框：strip_chrome.py 切极简档 -> --check -> 用切档后的 spec 再渲一遍，
     确认 chrome 字段撤干净、撤完还能出图。
  5. 转场（可选）：派生一份 2 镜小 spec 跑 `--video`，确认转场片内合成没崩。

退出码：0 全通；1 有步骤失败；2 环境缺 Pillow（连渲都渲不了）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "assets", "kit")
EXAMPLES = os.path.join(HERE, "assets", "examples")
RENDER = os.path.join(KIT, "render.py")
AUDIT = os.path.join(KIT, "audit.py")
STRIP = os.path.join(KIT, "strip_chrome.py")
SAMPLES = ["spec.sample.json", "spec.minimal.sample.json"]     # 档案档样张 + 极简档样张
W, H = 1920, 1080

_ok, _fail = [], []


def step(n, title):
    print(f"\n[{n}] {title}")


def good(msg):
    _ok.append(msg)
    print(f"    ✓ {msg}")


def bad(msg):
    _fail.append(msg)
    print(f"    ✗ {msg}")


def run(cmd, what):
    """跑一条子进程命令；失败时把 stderr 尾部打出来，便于定位。"""
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.time() - t0
    tail = (p.stdout.strip().splitlines() or [""])[-1]
    if p.returncode != 0:
        print("      " + " ".join(cmd[:3]) + " ...")
        err = (p.stderr or p.stdout or "").strip().splitlines()[-8:]
        for ln in err:
            print("      | " + ln)
        bad(f"{what}（退出码 {p.returncode}）")
        return None
    good(f"{what}  {dt:.1f}s" + (f"  · {tail}" if tail else ""))
    return p.stdout


def absify(spec, base):
    """示例里的媒体是相对 spec 文件所在目录写的；搬到临时目录后必须改成绝对路径，
    否则渲染器找不到图会静默画占位框、audit 才发现。

    只动渲染器自己会解析成路径的那几个键（与 render.resolve_media 一致）——
    slots 里别的字符串是文案/枚举（`kind: "bar"`），一个都不能碰。
    """
    for sc in spec.get("scenes", []):
        for k in ("bg", "sound", "media2"):
            v = sc.get(k)
            if isinstance(v, str) and v and not os.path.isabs(v):
                sc[k] = os.path.join(base, v)
        slots = sc.get("slots") or {}
        for k in ("image", "media", "left", "right"):
            v = slots.get(k)
            if isinstance(v, str) and v and not os.path.isabs(v):
                slots[k] = os.path.join(base, v)
    return spec


# ---------------------------------------------------------------- 1 依赖
def check_deps():
    step(1, "依赖")
    try:
        import PIL
    except ImportError:
        print("    ✗ 没有 Pillow：pip install pillow（不需要 numpy）")
        return 2
    good(f"Pillow {PIL.__version__}")
    ff = shutil.which("ffmpeg")
    if ff:
        good("ffmpeg 在（--video / --mp4 可跑）")
    else:
        print("    — 没有 ffmpeg：跳过转场那步（静帧、audit、去框不受影响）")
    return 0


# ---------------------------------------------------------------- 2 字体回退
def check_fonts():
    step(2, "字体回退（微软雅黑 / 苹方 / Noto）")
    sys.path.insert(0, KIT)
    import kit_common as c            # noqa: E402  type: ignore  同一份字体回退链，别另抄一遍

    hit = {}
    for weight in ("regular", "bold", "mono"):
        found = next((p for p in c.FONT_CANDIDATES[weight] if os.path.exists(p)), None)
        hit[weight] = found
        name = os.path.basename(found) if found else "（无，走 Pillow 内置）"
        print(f"    · {weight:7s} -> {name}")

    cjk = [p for w in ("regular", "bold") for p in [hit[w]] if p]
    if not cjk:
        bad("找不到任何中文字体：中文会渲成方框（Linux: apt install fonts-noto-cjk）")
        return False
    missing = [n for n, pat in (("微软雅黑", "msyh"), ("苹方", "PingFang"))
               if not any(pat.lower() in (hit[w] or "").lower() for w in ("regular", "bold"))]
    if missing:
        good(f"缺 {('、'.join(missing))}，已回退到 {os.path.basename(cjk[0])}（正常，不影响出图）")
    else:
        good(f"命中系统字体 {os.path.basename(cjk[0])}")

    # 豆腐块检测：字体缺 CJK 时所有汉字都渲成同一个 .notdef 方框，两个字的掩码会一模一样
    from PIL import Image, ImageDraw
    f = c.font(48, "regular")
    mask = lambda ch: bytes(f.getmask(ch))    # noqa: E731
    try:
        a, b = mask("中"), mask("文")
    except Exception as e:                     # noqa: BLE001
        bad(f"字形取不出来：{type(e).__name__}: {e}")
        return False
    if not a or a == b:
        bad(f"{os.path.basename(cjk[0])} 渲「中」「文」掩码相同/为空 → 可能是豆腐块")
        return False
    im = Image.new("RGB", (240, 90), "#07080A")
    ImageDraw.Draw(im).text((10, 20), "中文字幕", font=f, fill="#F2F2F2")
    if im.convert("L").getextrema()[1] == 7:   # 底色亮度 7，没变化就是没画出字
        bad("中文字幕没落画（整屏还是底色）")
        return False
    good("中文正常落画，不是豆腐块")
    return True


# ---------------------------------------------------------------- 3 渲染 + 自检
def check_render_and_audit(tmp):
    step(3, "渲染 + audit（两份示例 spec）")
    okall = True
    for name in SAMPLES:
        spec = os.path.join(EXAMPLES, name)
        out = os.path.join(tmp, name.replace(".json", ""))
        scenes = json.load(open(spec, encoding="utf-8-sig"))["scenes"]
        print(f"    — {name}（{len(scenes)} 镜）")
        if run([sys.executable, RENDER, spec, out + os.sep, "--png"], "render --png") is None:
            okall = False
            continue
        from PIL import Image
        broken = []
        for sc in scenes:
            p = os.path.join(out, f"{sc['id']}.png")
            if not os.path.exists(p):
                broken.append(f"{sc['id']} 没出图")
                continue
            with Image.open(p) as im:
                if im.size != (W, H):
                    broken.append(f"{sc['id']} 尺寸 {im.size} ≠ {W}×{H}")
                elif os.path.getsize(p) < 8000:
                    broken.append(f"{sc['id']} 只有 {os.path.getsize(p)} 字节，像空帧")
        if broken:
            bad("；".join(broken))
            okall = False
        else:
            good(f"{len(scenes)} 张静帧齐全且非空")
        if run([sys.executable, AUDIT, spec], "audit") is None:
            okall = False
        if run([sys.executable, AUDIT, spec, "--images", out + os.sep], "audit --images") is None:
            okall = False
    return okall


# ---------------------------------------------------------------- 4 去框
def check_strip_chrome(tmp):
    step(4, "去框（strip_chrome.py -> 极简档 -> 再渲一遍）")
    src = os.path.join(EXAMPLES, "spec.sample.json")
    minimal = os.path.join(tmp, "stripped.minimal.json")
    if run([sys.executable, STRIP, src, "-o", minimal], "strip_chrome -o") is None:
        return False
    if run([sys.executable, STRIP, minimal, "--check"], "strip_chrome --check") is None:
        return False

    spec = absify(json.load(open(minimal, encoding="utf-8")), os.path.dirname(src))
    json.dump(spec, open(minimal, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    residue = [f"{sc['id']}.{k}" for sc in spec["scenes"]
               for k in ("when", "rel", "source", "tc", "show_tc", "label_left",
                         "label_right", "brand", "strap", "strap_tab", "clock")
               if k in sc]
    if residue or spec.get("brand"):
        bad(f"切档后还留着 chrome 字段：{residue or 'spec 级 brand'}")
        return False
    if any(sc.get("disclaimer") is not False for sc in spec["scenes"]):
        bad("disclaimer 没有显式关掉（默认 true，极简档会多一行免责）")
        return False
    good(f"{len(spec['scenes'])} 镜 chrome 字段撤干净，disclaimer=false")

    out = os.path.join(tmp, "stripped_out")
    if run([sys.executable, RENDER, minimal, out + os.sep, "--png"], "极简档 render --png") is None:
        return False
    if run([sys.executable, AUDIT, minimal], "极简档 audit") is None:     # 撤干净后不能有残留 WARN
        return False
    return True


# ---------------------------------------------------------------- 5 转场
def check_video(tmp):
    step(5, "转场合成（2 镜派生 spec -> --video）")
    if not shutil.which("ffmpeg"):
        print("    — 没有 ffmpeg，跳过")
        return True
    src = os.path.join(EXAMPLES, "spec.sample.json")
    spec = absify(json.load(open(src, encoding="utf-8-sig")), os.path.dirname(src))
    scenes = spec["scenes"][:2]
    for i, sc in enumerate(scenes):
        sc["dur"] = 0.8
        sc["transition"] = {"type": "dissolve" if i == 0 else "cut", "duration": 0.2}
    short = os.path.join(tmp, "two_scene.json")
    json.dump({"canvas": {"w": W, "h": H, "fps": 30}, "scenes": scenes},
              open(short, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = os.path.join(tmp, "film")
    os.makedirs(out, exist_ok=True)
    film = os.path.join(out, "film.mp4")
    if run([sys.executable, RENDER, short, out + os.sep, "--video", film], "--video") is None:
        return False
    if not os.path.exists(film) or os.path.getsize(film) < 2000:
        bad("整片没落地或只有几字节")
        return False
    good(f"整片 {os.path.getsize(film) // 1024} KB（转场在片内合成，Σdur = {sum(s['dur'] for s in scenes):.1f}s）")
    return True


def main(argv):
    keep = "--keep" in argv
    with_video = "--no-video" not in argv
    t0 = time.time()
    print(f"explainer-landscape 冒烟测试 · {HERE}")
    print(f"python {sys.version.split()[0]}")

    rc = check_deps()
    if rc:
        return rc
    tmp = tempfile.mkdtemp(prefix="el-smoke-")
    try:
        if not check_fonts():
            return 1
        if not check_render_and_audit(tmp):
            return 1
        if not check_strip_chrome(tmp):
            return 1
        if with_video and not check_video(tmp):
            return 1
    finally:
        if keep:
            print(f"\n中间产物留着：{tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    dt = time.time() - t0
    print(f"\n结论：{len(_ok)} 项通过 / {len(_fail)} 项失败 · {dt:.1f}s")
    if _fail:
        for m in _fail:
            print(f"  ✗ {m}")
        return 1
    print("冒烟通了：示例 spec 能渲染、能自检、能切极简档；字体回退见上，不是豆腐块。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
