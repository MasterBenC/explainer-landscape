# explainer-landscape · 横版解说片模板

把选题做成 16:9「档案式」商业/财经解说：八种版式（巨数字卡、双栏证据、逐条揭示、时间轴、关系图、来源清单、数据图、图片镜）、两档 chrome（档案档 / 极简档）、可检查的动效节奏，外加一套 spec 渲染器。参数来自对一条 4 分 17 秒财经调查解说（48 镜）的逐镜拆解，并用两期真实成片（30 fps / 44 镜 / 5–6 分钟）回灌修正过——0.2.0 的改动清单见 `references/cases-2026-11.md`。

## 装

```bash
python install.py                 # 复制到 ~/.agents/skills、~/.claude/skills、~/.codex/skills
python install.py --target ~/.agents/skills
```

依赖：Python ≥ 3.9、Pillow；出 mp4 需要 ffmpeg；中文用系统字体（微软雅黑 / 苹方 / Noto）。

## 用

```bash
# 1. 从示例改出自己的分镜
cp assets/examples/spec.sample.json my_spec.json

# 2. 选 chrome：档案档（默认）还是极简档（只留章节牌 + 字幕，来源收片尾）
python assets/kit/strip_chrome.py my_spec.json -o my_spec.minimal.json
python assets/kit/strip_chrome.py my_spec.json --check        # 先看现在都有哪些角标

# 3. 出静帧，先看版式
python assets/kit/render.py my_spec.json out/ --png --contact

# 4. 自检
python assets/kit/audit.py my_spec.json

# 5. 出逐条揭示的片段（其余按 spec 在剪辑软件里落）
python assets/kit/render.py my_spec.json out/ --mp4
```

## spec 长什么样

> `canvas.fps` 从 0.2.0 起真正生效：写 30 就渲 30（示例文件仍是 24，那是参考片的基线）。
> 极简档不需要手删字段，跑 `strip_chrome.py` 即可。

```json
{
  "canvas": {"w": 1920, "h": 1080, "fps": 24},
  "scenes": [{
    "id": "s01", "dur": 6.0, "form": "bignum",
    "chapter": "线索一·爆料的媒体", "brand": "Anthropic",
    "when": "11-09", "rel": "两天前",
    "title": "董事会：对他有信心", "kicker": "英伟达董事会声明 · 2026-11-08",
    "subtitle": "两天前情况还比较乐观", "source": "画面：CNBC（2026-11-09）",
    "tc": "00:04.0",
    "slots": {"number": "17", "unit": "年", "caption": "他亲手创立、干了三十三年", "note": "董事会 11 席"},
    "motion": [{"item": "number", "at": 0.0, "kind": "appear", "easing": "instant", "dur": 0.0}]
  }]
}
```

## 里面有什么

| 文件 | 内容 |
|---|---|
| `SKILL.md` | 流程、硬规则、选版式 |
| `references/layout-spec.md` | 画布、颜色、chrome 坐标、字号阶梯、栅格 |
| `references/form-catalog.md` | 八种版式的线框图和槽位（含 `chart` 四种画法、`photo` 两种落法） |
| `references/motion-spec.md` | 出现/替换/消失、缓动、转场配比 |
| `references/pacing-spec.md` | 五幕结构、镜长分布、章节配比 |
| `references/depth-and-texture.md` | 深度交替、档案化、常驻页眉、下三分之一横条、证据标注 |
| `references/orchestration.md` | 和 rea-video / koubo / shotcraft 等技能的分工与换渲染层判据 |
| `references/qa-checklist.md` | 交付前自检 |
| `references/chrome-presets.md` | **两档 chrome 的字段对照**（档案档 / 极简档）与示例场景 |
| `references/cases-2026-11.md` | **0.2.0 的改动来源**：两期真实成片的 8 条用户口径 + 实测参数 |
| `assets/kit/render.py` | spec → 静帧 / 逐条揭示 mp4 / 拼图（`canvas.fps` 生效） |
| `assets/kit/audit.py` | spec → FAIL/WARN 报告 |
| `assets/kit/strip_chrome.py` | **一条命令把 spec 切到极简档 / 裸图档** |
| `assets/examples/spec.sample.json` | 8 镜示例（8 种版式各一镜） |
| `assets/examples/media/doc-page.png` | 示例图片镜用的占位资料页 |
| `assets/examples/out/` | 示例渲染结果（contact.png 是拼图） |

## 边界

只做画面。BGM、字幕文案断句、口播录制、成片合成不在范围内——那部分是 `koubo-animation-pipeline`（竖屏）和 `storyframe-video-skill` 的地盘。

## 变更

- **0.2.0（2026-11-18）** 案例回灌：`canvas.fps` 真正生效（旧版 spec 写 30 也会渲成 24）；
  新增 `strip_chrome.py` 与 chrome 两档；SKILL.md 增加屏幕文字预算、数字口径表、事实核对；
  `audit.py` 对极简档不再误报「有章节牌但没有品牌水印」。
- **0.1.0** 初版：48 镜参考片逐镜测量的版式、动效、节奏参数 + Pillow 渲染器。

