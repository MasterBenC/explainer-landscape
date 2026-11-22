#!/usr/bin/env python3
"""全链路冒烟测试：示例 spec -> 渲染 -> 自检 -> 去框，一条命令跑完，失败退出码非零。

    python smoke_test.py            # 默认：静帧 + audit + strip_chrome + 转场（有 ffmpeg 时）
    python smoke_test.py --no-video # 跳过转场/整片那步（没装 ffmpeg 或想更快）
    python smoke_test.py --keep     # 保留中间产物（默认跑完删临时目录）

除了"能不能跑通"，还带两条像素级回归：整幅出血图不许盖住字幕、顶部暗带按高度算。
要验版式和参数请跑 `assets/kit/audit.py`（含 `--images --strict`）与 `references/qa-checklist.md`。

五步各查什么：
  1. 依赖：Pillow 能不能 import；出 mp4 的 ffmpeg 有没有（没有只影响转场那步）。
  2. 字体：走渲染器同一条回退链（spec fonts -> 环境变量 -> 平台路径 -> fc-match），
     **回退到哪个字体要报出来**；一个 CJK 字形都没有才算失败。
  3. 渲染 + 自检：assets/examples/ 两份示例 spec 各渲一遍静帧，再跑 audit.py
     （`--images --strict`，有任何 WARN 就算失败）。
  4. 整幅出血 photo 回归：一镜不给 depth 的 photo，像素级验证字幕区仍有字、
     且顶部暗带只压到 ~46% 高度（P0-1 / P0-2 回归，别改回整幅盖住或被 W 带偏）。
  5. 去框：strip_chrome.py 切极简档 -> --check -> 用切档后的 spec 再渲一遍，
     确认 chrome 字段撤干净、撤完还能出图、且 audit --strict 无残留 WARN。
  6. 转场（可选）：派生一份 2 镜小 spec 跑 `--video`，确认转场片内合成没崩。

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

    # 这里必须问渲染器要结果，不能自己拿 FONT_CANDIDATES 判存在性：
    # 路径存在 ≠ 有中文字形（DejaVuSans 就在，纯拉丁），旧写法会假通过。
    hit = c.font_report()
    for weight in ("regular", "bold", "mono"):
        found = hit[weight]
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

    from PIL import Image, ImageDraw
    try:
        f = c.font(48, "regular")
    except SystemExit as e:          # 字体全缺时 kit_common 直接 SystemExit(2)
        bad(f"取字体失败（退出码 {e.code}），见上方 kit_common 打的候选清单")
        return False

    # 豆腐块检测：字体缺 CJK 时所有汉字都渲成同一个 .notdef 方框，两个字的像素会一模一样。
    # 别用 font.getmask(ch).tobytes()——ImagingCore 上没有 tobytes()，一调就 AttributeError。
    def glyph(ch):
        g = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(g).text((0, 0), ch, font=f, fill=255)
        return g.tobytes()

    try:
        a, b = glyph("中"), glyph("文")
    except Exception as e:                     # noqa: BLE001
        bad(f"字形取不出来：{type(e).__name__}: {e}")
        return False
    if not a.strip(b"\x00") or a == b:
        bad(f"{os.path.basename(cjk[0])} 渲「中」「文」像素相同/为空 → 可能是豆腐块")
        return False

    # 亮度判据：白色文字（#F2F2F2≈242）画到 #07080A 底（亮度≈7）上，最亮处必须远超底色。
    # 旧写法 getextrema()[1] == 7 太脆：抗锯齿/伽马一动就假失败，改成给个下限（> 50）。
    im = Image.new("RGB", (240, 90), c.BG)
    ImageDraw.Draw(im).text((10, 20), "中文字幕", font=f, fill=c.TEXT)
    from PIL import ImageStat
    top = int(ImageStat.Stat(im.convert("L")).extrema[0][1])   # getextrema 的返回值类型不干净，走 Stat
    if top <= 50:
        bad(f"中文字幕没落画（最亮只有 {top}，底色 7，像没画出字）")
        return False
    good(f"中文正常落画，不是豆腐块（最亮 {top}）")
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
        if run([sys.executable, AUDIT, spec, "--strict"], "audit --strict") is None:
            okall = False
        if run([sys.executable, AUDIT, spec, "--images", out + os.sep, "--strict"],
               "audit --images --strict") is None:
            okall = False
    return okall


# ---------------------------------------------------------------- 4 整幅出血 photo
def check_fullbleed_photo(tmp):
    """P0-1 / P0-2 回归：不给 depth 的 photo 是整幅出血镜。

    两个都容易改坏、且肉眼不一定当场发现，所以用像素判：
      1) 字幕必须仍然画在最上层。判据 = 字幕带里出现足够多的「中性近白」像素。
         字幕色 #F2F2F2（242,242,242）是中性灰白；示例底图是暖米色（R>G>B），
         一旦整幅图盖住字幕，这一带的近白中性像素会掉到 0。
      2) 顶部暗带高度必须按 H 算（int(H*scrim)≈497px），不能按 W（旧值 883px≈82% 高）。
         判据 = 上半区平均亮度明显低于下半区；暗带若被 W 带偏，下半区也会跟着暗。
    """
    step(4, "整幅出血 photo（P0-1 字幕不被盖 / P0-2 暗带按 H）")
    from PIL import Image

    media = os.path.join(EXAMPLES, "media", "archive-card.png")
    if not os.path.exists(media):
        bad(f"缺示例底图 {media}（示例素材不能删）")
        return False

    scene = {
        "id": "fb01", "dur": 4.0, "form": "photo",
        "chapter": "回归·全幅",
        "title": "整幅出血不许盖住标题",
        "subtitle": "这一行字幕必须清楚可见，不能被整幅图盖住",
        "source": "图：示例占位卡片（虚构素材）",
        "tc": "00:00.0", "show_tc": True,
        "slots": {"image": media, "caption": "整幅出血回归镜", "credit": "图：示例占位 · 2026-10-02"},
        "transition": {"type": "cut", "duration": 0},
    }
    spec = {"canvas": {"w": W, "h": H, "fps": 30}, "brand": "示例频道",
            "scenes": [scene]}
    sp = os.path.join(tmp, "fullbleed.json")
    json.dump(spec, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = os.path.join(tmp, "fullbleed_out")
    if run([sys.executable, RENDER, sp, out + os.sep, "--png"], "全幅镜 render --png") is None:
        return False

    png = os.path.join(out, "fb01.png")
    if not os.path.exists(png):
        bad("全幅镜没出图")
        return False

    # 字幕带：字幕字号 54、基线约 y=1000，取 y 930..1010 这一条
    band_box = (134, 930, 1706, 1010)
    with Image.open(png) as im:
        rgb = im.convert("RGB")
        band = rgb.crop(band_box)
        r_ch, g_ch, b_ch = band.split()
        near_white = 0
        for r, g, b in zip(r_ch.tobytes(), g_ch.tobytes(), b_ch.tobytes()):
            if min(r, g, b) >= 232 and max(r, g, b) - min(r, g, b) <= 8:
                near_white += 1
        gray = rgb.convert("L")

    def mean_lum(y0, y1) -> float:
        """一块区域的灰度均值（ImageStat.mean[0]，别用 resize(1,1) 取像素，类型不干净）。"""
        from PIL import ImageStat
        return float(ImageStat.Stat(gray.crop((134, y0, 1706, y1))).mean[0])

    top, bottom = mean_lum(0, 400), mean_lum(600, 900)

    if near_white < 2000:
        bad(f"字幕带上只剩 {near_white} 个近白像素（阈值 2000）→ 字幕被整幅图盖住了（P0-1 回归）")
        return False
    good(f"字幕在最上层（字幕带近白像素 {near_white}）")

    if not top < bottom * 0.75:
        bad(f"上半区亮度 {top} 没明显低于下半区 {bottom} → 顶部暗带高度算错了（P0-2 回归）")
        return False
    good(f"顶部暗带只压上半区（上 {top} / 下 {bottom}，按 H*scrim）")
    return True


# ---------------------------------------------------------------- 5 去框
def check_strip_chrome(tmp):
    step(5, "去框（strip_chrome.py -> 极简档 -> 再渲一遍）")
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
    if run([sys.executable, AUDIT, minimal, "--strict"], "极简档 audit --strict") is None:
        return False        # 撤干净后不能有残留 WARN：WARN 本身不导致失败，所以必须加 --strict
    return True


# ---------------------------------------------------------------- 5 转场
def check_video(tmp):
    step(6, "转场合成（2 镜派生 spec -> --video）")
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
        if not check_fullbleed_photo(tmp):
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
