---
name: explainer-landscape
description: 横版（16:9）解说视频的视觉模板与渲染工具：把选题或口播稿变成"档案式"商业/财经解读画面——八种版式（巨数字卡、双栏证据、逐条揭示、时间轴对比、关系图、结尾来源清单、数据图、图片镜）、可检查的动效与节奏参数、两档 chrome（档案档＝页眉日期戳/章节牌/来源行/时间码；极简档＝只留章节牌与字幕，图源收进片尾来源页）。当用户要做横版解说片、中视频、B站/YouTube 深度解说、商业/财经/调查类解读、信息流图表视频、口播配画面的分镜、档案式纪录片版式，或问"这条解说视频的画面怎么做"时使用。只负责画面；BGM、字幕文案、口播录制不在范围内。
---

# explainer-landscape：横版解说片画面模板

把一条选题做成"看起来像调查报道"的 16:9 画面。这套规范不是设计感，是**可复用的信息结构**：观众每一秒都知道"现在是什么时间、这是第几条线索、这句话的证据在哪"。

数据来源：对一条 4 分 17 秒的财经调查解说（黄仁勋/英伟达/Anthropic）做逐镜拆解，48 镜、24fps、960×544，测得版式坐标、字号、动效事件与镜头节奏后归一化到 1920×1080；再用两期真实成片（30fps、44 镜、5–6 分钟）回灌修正。

## 0. 先判断该不该用

适用：横版、有旁白驱动、以"讲清一件事"为目标的解说片——商业解读、财经调查、科技科普、人物档案、中视频/长视频深度解说。

不适用：竖屏短视频（用 `koubo-animation-pipeline`）、纯 Vlog、产品广告、无旁白的混剪。

要和 `rea-video` / `koubo-animation-pipeline` / `video-shotcraft` 拼一条完整生产线时，分工与"什么时候该换 Remotion"的判据见 `references/orchestration.md`。

## 0.5 开跑前 30 秒环境检查

```bash
python -c "import PIL; print('Pillow', PIL.__version__)"   # 必须
ffmpeg -version | head -1                                  # 只有出 mp4 才需要
fc-list :lang=zh | head -3                                 # Linux 必查，空 = 中文渲成豆腐块
```

- 缺 Pillow：`pip install pillow`。**不需要 numpy**，所有检查都是纯 PIL。
- Linux 缺中文字体：`apt install fonts-noto-cjk`。找不到任何 CJK 字体时 `render.py` 会打
  ERROR 并以退出码 2 终止（不会静默出一屏 □□□ 还报成功）。
- `--video` 对 ffmpeg 版本没有特殊要求：转场是渲染器逐帧合成的，不走 `xfade` 滤镜。
- spec 存 UTF-8 即可；Windows 记事本写的 BOM 也能读（`utf-8-sig`）。

## 1. 五步流程

```bash
# 下面命令里的 <skill-dir> = 本 skill 的安装目录（如 ~/.claude/skills/explainer-landscape）；
# spec 和 out/ 都放你自己的目录，不需要 cd 进 skill 目录

# ① 写分镜 spec，一个 scene 一段画面
#    字段全表见 references/spec-schema.md（漏字段/拼错键名是最常见的返工原因）

# ② 渲染静帧看版式（先看图，再上时间线）
python "<skill-dir>/assets/kit/render.py" spec.json out/ --png

# ③ 自检：字段、转场、版式、节奏；有静帧时再加像素检查
python "<skill-dir>/assets/kit/audit.py" spec.json
python "<skill-dir>/assets/kit/audit.py" spec.json --images out/     # 红占比 / 填充率 / 亮度

# ④ 出片，两条路：
python "<skill-dir>/assets/kit/render.py" spec.json out/ --mp4                  # 分镜片段（不含转场，给剪辑软件）
python "<skill-dir>/assets/kit/render.py" spec.json out/ --video out/final.mp4   # 整片（转场在片内合成）

# ⑤ 回看：整片抽帧拼图，确认没有一屏是"只有背景和一句话"
python "<skill-dir>/assets/kit/render.py" spec.json out/ --contact
```

`--video` 的转场吃掉的是**前一镜的尾部**画面，输出总时长严格等于各镜 `dur` 之和
（不是像 ffmpeg `xfade` 那样每接一次就短一个转场）。要拿它给已有口播盲拼时记住：
画面切点会比台词早 `transition.duration` 秒，先对一遍再导出。

## 2. 硬规则（不可改）

| 项 | 值 | 为什么 |
|---|---|---|
| 画布 | 1920×1080；**30fps 优先**，由 `canvas.fps` 指定（缺省按 30 兜底）；24/25fps 只在素材本来就是那个帧率时用 | 2026-11 两期实测：素材 30fps，成片也交 30 |
| 底色 | `#07080A`（近黑，略带蓝） | 原片 48 镜里有 34 镜是这个底色区间 |
| 强调色 | `#E0322C` 只用在一处 | 原片红色只出现在"关键数字"和"章节分隔符"，全片用量 < 2% |
| 左边距 | 134px（内容右边界 1786px） | 原片文字起点集中在 0.05–0.09 区间 |
| 字幕基线 | y=1000，字号 54，最多两行 | 两行时上移到 930，行距 1.35 |
| 底部保留区 | 档案档：y > 860 只放 chrome；**极简档：底部 130px 只放字幕，来源/免责/时间码/横条全撤** | 极简档就是"底部只有字幕" |
| 每屏一个论点 | 一屏只推进一件事 | 原片中位镜长 3.2 秒，塞两个论点就会糊 |
| 屏幕文字预算 | 一镜最多「1 个主信息 + 1 条副信息」；连续三镜都是"标题+副标+来源"就该删字 | 用户从"字太多"改到"全删"，最后收敛到只留标题层 |

完整参数（坐标、字号阶梯、颜色 token）见 `references/layout-spec.md`。

## 2.5 chrome 两档：先选档，再排序（2026-11 案例的直接结论）

`render.py` 的常驻元素全是可选字段（写了就画），所以"要不要角标"是改 spec，不是改代码：

| 档 | 画什么 | 适合 |
|---|---|---|
| **档案档** `when` + `rel` + `source` + `tc` + `label_*` + `brand`（可选 `strap` / `strap_tab` / `clock`） | 日期戳、相对时间、来源行、右下时间码、栏目标签、下三分之一横条 | 素材以截图为主、需要随时证明"这是哪天哪家"的调查片 |
| **极简档** 只留 `chapter` + `subtitle` | 章节牌 + 字幕，别的全撤，来源集中到片尾 `sources` 镜 | **用户实际选择的那一档**：档案感来自结构和节奏，不来自角标 |

切档一条命令（不动版式，只改 chrome 字段）：

```bash
python "<skill-dir>/assets/kit/strip_chrome.py" my_spec.json -o my_spec.minimal.json   # 极简档
python "<skill-dir>/assets/kit/strip_chrome.py" my_spec.json --check                   # 先看现在都有哪些角标
```

两个坑：`disclaimer` 默认是 **true**（不写也会在底部画一行免责声明），极简档必须显式关掉——
`strip_chrome.py` 已经代劳；`show_tc` 不写就不画时间码，但写了 `tc` 别忘了它。字段全表与示例见
`references/chrome-presets.md`，可运行的极简档样张是 `assets/examples/spec.minimal.sample.json`。

## 3. 选版式

八种版式，按"这句话在干什么"选，不按好看选：

| 版式 | 什么时候用 | 关键槽位 |
|---|---|---|
| `bignum` 巨数字卡 | 一个数字就能说明问题：17年、$2500万、3天 | `number` / `unit` / `caption` / `note` |
| `evidence` 双栏证据 | 有一个可展示的源：新闻页、推文、公告、官网 | `left` 画面 / `right` 截图 + `attrib` |
| `list` 逐条揭示 | 三个并列原因、三条线索、三个疑点 | `items[]`，每条带 `at` 出现时间 |
| `timeline` 时间轴对比 | 前后变化：2024 的 $64万 → 2025 的 $600万 | `points[]`（`label` / `value`）/ `delta` |
| `relation` 关系图 | 谁和谁有关：人脉、捐款、两届政府的人 | `center` + `satellites[]` |
| `sources` 结尾清单 | 收尾：结论 + 全部出处（**必须是最后一镜**） | `closing` / `blocks[]` |
| `chart` 数据图 | 数据叙事主力：`bar` / `line` / `donut` / `kpi`，数字直接画出来，不靠截图 | `kind` / `data[]` / `chart_title` |
| `photo` 图片镜 | 图文并茂主力：白底信息图用 `framed:true` 放右侧卡片，暗调照片走整幅出血 | `image` / `caption` / `credit` |

后两种是"能画出来就别用嘴说"：数据用 `chart` 直接画（`bar` / `line` / `donut` / `kpi`），现场用 `photo` 直接看。四种数据图和两种图片落法见 `references/form-catalog.md` 第 7、8 节。

## 3.5 深度、质感与常驻图层（决定"像不像成片"）

| 能力 | 用法 | 为什么 |
|---|---|---|
| **深度交替** | `depth: "bg"` 图铺满 / `depth: "fg"` 图做前景卡浮起，两种交替（还有 `split` 左文右图） | 全片一个密度会显得单调；实测 bg 填充 0.81–0.92、fg 0.31–0.34 |
| **档案化** | `archival: {desat, warm, dark}` + 颗粒 + 门闪，只作用在图片层 | "旧"要旧在素材，字必须锐利；这是历史感的来源 |
| **常驻页眉** | `label_left` / `label_right` | 参考片的识别元素，全程在 |
| **下三分之一横条** | `strap` / `strap_tab` / `clock` | 一屏一个事实，横条只写这一屏在讲什么 |
| **证据标注** | `callouts: [{x,y,dx,dy,text}]` | 图片来源要指得出来，引线先长、标签后出 |

细节与自查阈值见 `references/depth-and-texture.md`。

## 4. 动效与节奏

- 入场 0.25–0.45 秒；`instant` 占三分之一（硬出现，像翻档案），其余 `ease: out` / `in_out`。
- 一镜里的元素是**逐条换**，不是整屏淡入：appear → change → disappear 循环，长镜里每 2–3 秒动一次。
- 转场写在 scene 上：`"transition": {"type": "fade", "duration": 0.5}`，`type` 取
  `cut` / `fade` / `dissolve` / `wipe` / `blur`（`blur` 在渲染器里走黑场）；不写等于 `cut`。
- 转场配比（按 48 镜实测）：硬切 50%、闪白/黑场 15%、划像 15%、虚焦 12%、叠化 8%。
- 镜头长度：长解释镜 5–23 秒，短证据插 1–5 秒，两者交替；不要连续三镜同长度。
- 每分钟约 11 刀。

细则见 `references/motion-spec.md` 与 `references/pacing-spec.md`。

## 5. 五幕结构

| 幕 | 占比 | 画面在做的事 |
|---|---|---|
| 冷开场 | 0–3% | 一句话结论 + 一张硬证据（人物卡或新闻页） |
| 铺垫与转折 | 3–18% | 日期戳快速跳（时间线 5%）→ 事件落地（转折 6%）→ 把观众的疑问问出来（提问 4%） |
| 线索段 | 18–63% | 每 30–40 秒一个章节牌（线索一/二/三），每节 2–4 个子论点，每个子论点配一张证据 |
| 后果与反证 | 63–90% | 巨数字卡 + 关系图回答"所以呢、谁得利"（17%），再用时间轴/关系图反证主角自己也下了注（10%） |
| 结语 + 来源 | 90–100% | 左侧结语大字，右侧来源清单（`sources` 必须是最后一镜） |

七段细分的时间刻度与"一镜的信息量"上限见 `references/pacing-spec.md`。

## 6. 交付前自检

跑 `audit.py`（有静帧时加 `--images out/`），再人工过一遍 `references/qa-checklist.md`。三条最常犯的：

1. 一屏放了两个论点 → 拆成两镜。
2. 数字卡没有单位或没有注解 → 观众记不住。
3. 连续三镜都是 `evidence` 双栏 → 换一次 `bignum` 或 `list` 打破节奏。

`audit.py` 现在会直接抓这几类**静默失效**（以前只有退出码 0，看不出来）：

- `motion` 里写 `easing` / `kind`（渲染器只读 `item` / `at` / `dur` / `ease`）；
- `ease: "ease_out"` 这类值（会退化成 linear，写法是 `out`）；
- `item: "num"`（巨数字卡的槽位叫 `number`）；`sources` 不是最后一镜；
- 极简档忘了 `"disclaimer": false`，或残留 `source` / `tc` / `strap`；
- `transition.duration ≥ dur`、`bar` 里两个 `highlight`、`callout` 坐标越界。

另外两条是 2026-11 案例新增的，都是**非画面**问题但会毁掉片子：

4. **数字口径表**：口播、字幕、画面三个地方的数字必须逐字一致。开拍前先写一张
   `原文 → 定稿` 对照表（例："两千多张 5090" → "六百多张"；"两万块" → "几万块"），
   三处照抄。对不上就是观众眼里的造假。
5. **事实核对**：每一个"谁干的/哪一天/多少钱"都要落到一手来源；报道口径要标"据……报道"，
   查不到的一律不上屏。宁可少一个画面，不要多一个错误。

## 7. 不做什么

- 不做花字、不做贴纸、不做表情包：这套风格的克制就是它的可信度。
- 不使用渐变背景、发光、粒子：原片背景是纯色近黑，动的是内容不是背景。
- 不用超过两种字体：中文一种（思源黑体/微软雅黑），数字一种（等宽或几何无衬线）。
- 不把来源行写成"网络"：每一张图都要能追到机构 + 日期。
- **不写"已授权"**：没有授权文件就别在署名里声称。音乐署名只写「曲名 — 作者」。

## 8. 案例回灌与版本

- `references/cases-2026-11.md`：0.2.0 的全部改动来源（档案002 上下两期的真实返工，
  8 条用户口径 + 实测参数 + 这一版修掉的 bug）。**新片开工前值得读一遍。**
- `references/spec-schema.md`：spec 字段全表（顶层 / 场景公共 / 8 种版式的槽位与默认值）。
- `references/chrome-presets.md`：两档 chrome 的字段对照与示例。
- 0.3.0 变更：`--video` 改走 `render_film`（转场片内合成，总时长 = Σdur，不再有 xfade 吃时长）；
  删掉 `concat_with_transitions`；`--floorplan` 归正为 `--contact`（旧名保留为别名）；
  默认帧率 30；`count-up` 改为显式 `count: true` 才开；`camera` 默认关；
  无 CJK 字体时报错退出；`clock` 真正落画；`strip_chrome` 补 `strap`/`strap_tab`/`clock`；
  `audit.py` 补 20+ 条机器检查与 `--images` 像素检查；新增 `spec-schema.md` 与极简档样张。
- 0.2.0 变更：`canvas.fps` 真正生效（旧版写 30 渲成 24）；新增 `strip_chrome.py`；
  新增 chrome 两档、屏幕文字预算、数字口径与事实核对四节；`audit.py` 对极简档不再误报品牌水印。
