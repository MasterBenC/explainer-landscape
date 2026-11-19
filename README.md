# explainer-landscape · 横版解说片模板

把选题做成 16:9「档案式」商业/财经解说：八种版式（巨数字卡、双栏证据、逐条揭示、时间轴、关系图、来源清单、数据图、图片镜）、两档 chrome（档案档 / 极简档）、可检查的动效节奏，外加一套 spec 渲染器。参数来自对一条 4 分 17 秒财经调查解说（48 镜）的逐镜拆解，并用两期真实成片（30 fps / 44 镜 / 5–6 分钟）回灌修正过——0.2.0 的改动清单见 `references/cases-2026-11.md`，0.3.0 见文末。

## 装

```bash
python install.py                 # 复制到 ~/.agents/skills、~/.claude/skills、~/.codex/skills
python install.py --target ~/.agents/skills
```

依赖：Python ≥ 3.9、Pillow（**不需要 numpy**）；出 mp4 需要 ffmpeg；中文用系统字体
（微软雅黑 / 苹方 / Noto）。没有 CJK 字体时渲染器会直接报错退出，不会静默出方框。

## 用

```bash
cd <skill_dir>          # 本 skill 的安装目录；下面命令里的 assets/kit/... 都相对它

# 1. 从示例改出自己的分镜（9 镜 / 48.5s 的版式样张；极简档看 spec.minimal.sample.json）
cp assets/examples/spec.sample.json my_spec.json
cp -r assets/examples/media .        # 示例 spec 的图按 spec 文件所在目录解析，必须一起拷过来

# 2. 选 chrome：档案档（默认）还是极简档（只留章节牌 + 字幕，来源收片尾）
python assets/kit/strip_chrome.py my_spec.json -o my_spec.minimal.json
python assets/kit/strip_chrome.py my_spec.json --check        # 先看现在都有哪些角标

# 3. 出静帧，先看版式
python assets/kit/render.py my_spec.json out/ --png --contact

# 4. 自检（有静帧时加 --images 查红占比/填充率/亮度）
python assets/kit/audit.py my_spec.json --images out/

# 5a. 出分镜片段（不含转场，给剪辑软件）
python assets/kit/render.py my_spec.json out/ --mp4

# 5b. 或直接出整片（转场在片内合成，总时长 = Σdur）
python assets/kit/render.py my_spec.json out/ --video out/final.mp4
```

## spec 长什么样

> `canvas.fps` 从 0.2.0 起真正生效；0.3.0 起缺省值改成 30（横版优先 30fps，
> 24/25 只在素材本来就是那个帧率时用）。字段全表见 `references/spec-schema.md`。
> 极简档不需要手删字段，跑 `strip_chrome.py` 即可。

```json
{
  "canvas": {"w": 1920, "h": 1080, "fps": 30},
  "scenes": [{
    "id": "s01", "dur": 6.0, "form": "bignum",
    "chapter": "线索一·爆料的媒体", "brand": "Anthropic",
    "when": "11-09", "rel": "两天前",
    "title": "董事会：对他有信心", "kicker": "英伟达董事会声明 · 2026-11-08",
    "subtitle": "两天前情况还比较乐观", "source": "画面：CNBC（2026-11-09）",
    "tc": "00:04.0", "show_tc": true,
    "slots": {"number": "17", "unit": "年", "caption": "他亲手创立、干了三十三年", "note": "董事会 11 席"},
    "motion": [{"item": "number", "at": 0.0, "dur": 0.0, "ease": "instant"}],
    "transition": {"type": "fade", "duration": 0.5}
  }]
}
```

## 里面有什么

| 文件 | 内容 |
|---|---|
| `SKILL.md` | 流程、环境检查、硬规则、选版式、五幕结构 |
| `references/spec-schema.md` | **spec 字段全表**（顶层 / 场景公共 / 8 种版式槽位 / 10 个坑） |
| `references/layout-spec.md` | 画布、颜色、chrome 坐标、字号阶梯、栅格 |
| `references/form-catalog.md` | 八种版式的线框图和槽位（含 `chart` 四种画法、`photo` 两种落法） |
| `references/motion-spec.md` | 动效字段、自动排布、`beats`、转场结构、动画禁区 |
| `references/pacing-spec.md` | 七段叙事结构（合计 100%）、镜长分布、章节配比、一镜信息量 |
| `references/depth-and-texture.md` | 深度交替、档案化、常驻页眉、下三分之一横条、证据标注 |
| `references/orchestration.md` | 和 rea-video / koubo / shotcraft 等技能的分工与换渲染层判据 |
| `references/qa-checklist.md` | 交付前自检（分档案档 / 极简档） |
| `references/chrome-presets.md` | **两档 chrome 的字段对照**（档案档 / 极简档）与示例场景 |
| `references/cases-2026-11.md` | 0.2.0 的改动来源：两期真实成片的 8 条用户口径 + 实测参数 |
| `assets/kit/render.py` | spec → 静帧 / 分镜 mp4 / 整片（转场片内合成）/ 拼图 |
| `assets/kit/audit.py` | spec → FAIL/WARN + `--images` 像素检查 |
| `assets/kit/strip_chrome.py` | 一条命令把 spec 切到极简档 / 裸图档 |
| `assets/examples/spec.sample.json` | 9 镜档案档样张（八种版式 + 一镜 depth fg，含转场 / strap / callouts） |
| `assets/examples/spec.minimal.sample.json` | 4 镜极简档样张（只留章节牌 + 字幕） |
| `assets/examples/make_media.py` | 生成两张占位图（纯 Pillow，ASCII 文本） |
| `assets/examples/media/doc-page.png` | 「公告页」占位图（photo framed / evidence 右栏） |
| `assets/examples/media/archive-card.png` | 「旧资料卡」占位图（depth bg / fg、archival 演示） |
| `assets/examples/out/` | 示例渲染结果（`contact.png` 是拼图） |

## 边界

只做画面。BGM、字幕文案断句、口播录制、成片合成不在范围内——那部分是 `koubo-animation-pipeline`（竖屏）和 `storyframe-video-skill` 的地盘。

## 变更

- **0.3.0（2026-11-18）** 按外部评审修了一轮：
  `--video` 改走 `render_film`（转场在片内逐帧合成，总时长严格 = Σdur；删掉会吃掉时长的
  `concat_with_transitions` 与 xfade 依赖）；`--floorplan` 归正为 `--contact`（旧名保留别名）；
  默认帧率 24 → **30**；`count-up` 改成显式 `count: true`；`camera` 默认关并写清范围；
  无 CJK 字体时报错退出；`clock` 真正落画；`strip_chrome` 补 `strap`/`strap_tab`/`clock`；
  `install.py` 没有目标目录时回退创建；`audit.py` 补 20+ 条机器检查（转场、单位、sources 位置、
  极简档残留、motion 键名/缓动值/item 名、fps）并新增 `--images` 像素检查；
  新增 `references/spec-schema.md`、极简档样张、占位图生成脚本；示例把 `sources` 移到最后、
  改 30fps、补转场与 depth。
- **0.2.0（2026-11-18）** 案例回灌：`canvas.fps` 真正生效（旧版 spec 写 30 也会渲成 24）；
  新增 `strip_chrome.py` 与 chrome 两档；SKILL.md 增加屏幕文字预算、数字口径表、事实核对；
  `audit.py` 对极简档不再误报「有章节牌但没有品牌水印」。
- **0.1.0** 初版：48 镜参考片逐镜测量的版式、动效、节奏参数 + Pillow 渲染器。
