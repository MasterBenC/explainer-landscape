# explainer-landscape · 横版解说片模板

把选题做成 16:9「档案式」商业/财经解说：八种版式（巨数字卡、双栏证据、逐条揭示、时间轴、关系图、来源清单、数据图、图片镜）、两档 chrome（档案档 / 极简档）、可检查的动效节奏，外加一套 spec 渲染器。参数来自对一条 4 分 17 秒财经调查解说（48 镜）的逐镜拆解，并用两期真实成片（30 fps / 44 镜 / 5–6 分钟）回灌修正过——0.2.0 的改动清单见 `references/cases-2026-11.md`，0.3.0 见文末。

## 装

```bash
python install.py                 # 复制到 ~/.agents/skills、~/.claude/skills、~/.codex/skills
python install.py --target ~/.agents/skills
python install.py --dry-run       # 只打印会装什么 / 会改什么，一个文件都不动
python install.py --force         # 真的同步成源目录的样子（覆盖差异文件、删除源里没有的文件）
```

安装默认是**安全模式**：已装目录里你自己改过的 `SKILL.md`、自己加的 spec，只要内容和源不同就
**跳过并警告**（会列出差异文件名），不覆盖、不删除；`--link` 的目标已存在时也要求显式
`--force`。加了 `--force` 才覆盖 / 删除，而且动每个文件之前先写一份 `.bak`（旧目录改名
`<name>.bak`，不是 rmtree），升级失败可以直接回滚。

依赖：

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | ≥ 3.9 | 只用标准库 |
| **Pillow** | **≥ 10.1** | `pip install "pillow>=10.1"`。**不需要 numpy**。低于 10.1 的版本没有 `ImageFont.load_default(size=)` 等 API，等宽兜底会抛错 |
| ffmpeg | 任意 | 只有出 `--mp4` / `--video` 才要；转场是渲染器逐帧合成的，不走 `xfade`，不吃版本 |
| 中文字体 | 任意 CJK 字体 | 见下 |

字体回退顺序（`assets/kit/kit_common.py` 实现）：spec 顶层 `fonts` 字段 → 环境变量
`EXPLAINER_FONT` / `EXPLAINER_FONT_BOLD` / `EXPLAINER_FONT_MONO` → 各平台候选路径 →
`fc-match 'sans:lang=zh'` 兜底。**最后还会实测字形**（渲「中」「文」两个字比对像素）——
路径存在但没有中文字形的字体（DejaVu 就是）会被跳过。一个可用 CJK 字体都找不到时，
`render.py` 打 ERROR 并以退出码 2 终止，不会静默出一屏 □□□。

各平台装字体：

```bash
sudo apt install fonts-noto-cjk        # Debian / Ubuntu
sudo dnf install google-noto-cjk-fonts # Fedora / RHEL
sudo pacman -S noto-fonts-cjk          # Arch
brew install --cask font-noto-sans-cjk # macOS（或用系统自带苹方）
# Windows 自带微软雅黑，无需安装
```

仓库里**不提交任何字体二进制**（`.otf/.ttf/.ttc`）。要指定字体就写 spec 的 `fonts`：

```json
{"fonts": {"regular": "/path/NotoSansCJK-Regular.ttc", "bold": "/path/NotoSansCJK-Bold.ttc"}}
```

## 用

```bash
# 下面命令里的 <skill-dir> = 本 skill 的安装目录；spec 和 out/ 放你自己的目录

# 1. 从示例改出自己的分镜（9 镜 / 51.4s 的版式样张；极简档看 spec.minimal.sample.json）
#    示例里的公司/人物/频道全是虚构的（北岭数据、周立言、远山观察），照抄不会撞到真人真事
cp assets/examples/spec.sample.json my_spec.json
cp -r assets/examples/media .        # 示例 spec 的图按 spec 文件所在目录解析，必须一起拷过来

# 2. 选 chrome：档案档（默认）还是极简档（只留章节牌 + 字幕，来源收片尾）
python "<skill-dir>/assets/kit/strip_chrome.py" my_spec.json -o my_spec.minimal.json
python "<skill-dir>/assets/kit/strip_chrome.py" my_spec.json --check        # 先看现在都有哪些角标

# 3. 出静帧，先看版式
python "<skill-dir>/assets/kit/render.py" my_spec.json out/ --png --contact

# 4. 自检（有静帧时加 --images 查红占比/填充率/亮度）
python "<skill-dir>/assets/kit/audit.py" my_spec.json --images out/ --strict   # --strict：WARN 也算失败
#    退出码：0 通过（或只有 WARN）；1 有 FAIL；2 参数写错。
#    --images 目录不存在、或某镜的渲染图缺失，都记 FAIL——"什么都没查到"不算通过。

# 5a. 出分镜片段（不含转场，给剪辑软件）
python "<skill-dir>/assets/kit/render.py" my_spec.json out/ --mp4

# 5b. 或直接出整片（转场在片内合成，总时长 = Σdur）
python "<skill-dir>/assets/kit/render.py" my_spec.json out/ --video out/final.mp4
```

装完想确认"这台机器能跑通"，跑一条全链冒烟（示例 spec → 渲染 → 自检 → 去框 → 转场）：

```bash
python "<skill-dir>/smoke_test.py"        # 全通退出码 0；缺 Pillow 退出码 2，其余失败退出码 1
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
    "chapter": "线索一·公告本身", "brand": "远山观察",
    "when": "10-02", "rel": "当天",
    "title": "董事会：计划之内", "kicker": "北岭数据董事会公告 · 2026-10-02",
    "subtitle": "公告只有四句，没有解释", "source": "画面：年度发布回放（虚构素材 · 2026-10-02）",
    "tc": "00:04.0", "show_tc": true,
    "slots": {"number": "33", "unit": "年", "caption": "他亲手创立、干了三十三年", "note": "董事会 11 席"},
    "motion": [{"item": "number", "at": 0.0, "dur": 0.0, "ease": "instant"}],
    "transition": {"type": "fade", "duration": 0.5}
  }]
}
```

## 里面有什么

| 文件 | 内容 |
|---|---|
| `SKILL.md` | 流程、环境检查、硬规则、选版式、五幕结构（粗粒度，与八段一一对上） |
| `references/spec-schema.md` | **spec 字段全表**（顶层 / 场景公共 / 8 种版式槽位 / 10 个坑） |
| `references/layout-spec.md` | 画布、颜色、chrome 坐标、字号阶梯、栅格 |
| `references/form-catalog.md` | 八种版式的线框图和槽位（含 `chart` 四种画法、`photo` 两种落法） |
| `references/motion-spec.md` | 动效字段、自动排布、`beats`、转场结构、动画禁区 |
| `references/pacing-spec.md` | 八段叙事结构（合计 100%，含五幕 ↔ 八段对照）、镜长分布、章节配比、一镜信息量 |
| `references/depth-and-texture.md` | 深度交替、档案化、常驻页眉、下三分之一横条、证据标注 |
| `references/orchestration.md` | 和 rea-video / koubo / shotcraft 等技能的分工与换渲染层判据 |
| `references/qa-checklist.md` | 交付前自检（分档案档 / 极简档） |
| `references/chrome-presets.md` | **两档 chrome 的字段对照**（档案档 / 极简档）与示例场景 |
| `references/cases-2026-11.md` | 0.2.0 的改动来源：两期真实成片的 8 条用户口径 + 实测参数 |
| `smoke_test.py` | 全链冒烟：示例 spec → 渲染 → audit → 去框 → 转场，附字体回退检查 |
| `assets/kit/render.py` | 入口：CLI / spec 加载 / 按选项调各层（实现在下面五个子模块） |
| `assets/kit/kit_common.py` | 公共工具：设计 token、字体回退、缓动、文本排版、图/底色缓存、档案化 |
| `assets/kit/kit_chrome.py` | chrome 模板：页眉 / 章节牌 / 字幕 / 来源行 / 时间码 / kicker / strap / callouts |
| `assets/kit/kit_forms.py` | 版式渲染器：八种 form + `FORMS` 注册表 |
| `assets/kit/kit_scene.py` | 单镜合成：depth（bg / split / fg）+ 一帧的组装顺序 |
| `assets/kit/kit_film.py` | 视频转场合成：`--mp4` 分镜片段、`--video` 整片、推镜、拼图 |
| `assets/kit/audit.py` | spec → FAIL/WARN + `--images` 像素检查 |
| `assets/kit/strip_chrome.py` | 一条命令把 spec 切到极简档 / 裸图档 |
| `assets/examples/spec.sample.json` | 9 镜档案档样张（八种版式 + 一镜 depth fg，含转场 / strap / callouts） |
| `assets/examples/spec.minimal.sample.json` | 4 镜极简档样张（只留章节牌 + 字幕） |
| `assets/examples/make_media.py` | 生成两张占位图（纯 Pillow，ASCII 文本） |
| `assets/examples/media/doc-page.png` | 「公告页」占位图（photo framed / evidence 右栏） |
| `assets/examples/media/archive-card.png` | 「旧资料卡」占位图（depth bg / fg、archival 演示） |
| `assets/examples/out/` | 示例渲染结果（`contact.png` 是拼图） |
| `.github/workflows/ci.yml` | CI 门禁：冒烟测试 + `audit --strict` + 脱敏检查 + 字体二进制检查 |

## 边界

只做画面。BGM、字幕文案断句、口播录制、成片合成不在范围内——那部分是 `koubo-animation-pipeline`（竖屏）和 `storyframe-video-skill` 的地盘。

## 变更

- **0.3.2（2026-11-22）** 止血版：修渲染 P0 + 文档/实现归口，加回归与 CI 门禁。
  - **整幅出血图不再盖住字幕/标题**：`photo` 不给 `depth` 时的整幅底图（含无图占位）改由
    `kit_scene.render_scene` 在 chrome 之前铺层（`BACKDROPS` 注册表），以前它是在 FORMS 里画的，
    顺序在字幕之后，字幕会被自己的配图盖掉。
  - **顶部暗带按高度算**：`int(W * scrim)`（883px，等于 82% 画面高）→ `int(H * scrim)`（497px）。
  - **栏内文本不再越界/重叠**：`draw_text` 新增 `max_w`，`evidence.quote` / `framed` caption /
    `list` 条目按真实栏宽折行；引文折两行时署名自动下移（以前直接压在引文上）。
  - **字体回退跨平台**：spec `fonts` → 环境变量 → 各平台候选路径（Windows / macOS / Debian·
    Ubuntu / Fedora·RHEL `google-noto-cjk` / Arch `noto-cjk` / openSUSE 文泉驿）→
    `fc-match 'sans:lang=zh'` 兜底，并**实测字形**（DejaVu 这类「文件在、没中文」的会被跳过）。
    找不到就 ERROR + 退出码 2。依赖写明 **Pillow ≥ 10.1**；仓库不带字体二进制。
  - **`install.py` 不再可能删源码**：目标目录名固定为 `explainer-landscape`（zip 解压带的
    `-main` / `-0.3.2` 后缀不再传染），删除/覆盖前比对 `realpath`，相同或嵌套就跳过并提示。
  - **示例 spec 全部脱敏**：两份示例改成分虚构公司/人物/频道（北岭数据 / 周立言 / 远山观察），
    并修掉时间线矛盾、柱状图缺年份、1.5 秒塞爆一屏、四处重复文案；`out/` 预览图同步重渲。
  - **口径归口**：`dur` 缺省统一 `DEFAULT_DUR=4.0`（render / kit_scene / kit_film / audit 同一常量），
    `audit.py` 把「缺 dur」判 FAIL；字幕阈值按 54px / 1572px 实测（单行 29 字 WARN、两行 58 字 FAIL），
    折行超限会 warn 而不是静默截断；`line` 图上限 4 → 6 点；`camera` 阈值文案统一 0.02；
    最后一镜写非 `cut` 转场发 WARN；`strip_chrome.py` 用 `utf-8-sig` 读，撤 `source` 时把逐镜来源
    去重并进片尾 `sources` 镜（无 sources 镜则明确警告，不再静默丢）。
  - 文档如实化：颗粒是**按镜静态**（每镜一张、2.2% 叠加），删掉「逐帧轮换 / 门闪」的说法。
  - 测试与门禁：`smoke_test.py` 新增整幅出血 `photo` 像素回归（字幕带近白像素数 + 顶部暗带
    明暗对比），字体检测改走渲染器同一条回退链，豆腐块判据从 `== 7` 放宽到 `> 50`，
    `audit.py` 全部调用加 `--strict`；新增 GitHub Actions（两档 Python × 冒烟 + 脱敏/字体二进制门禁）。
- **0.3.1（2026-11-19）** 结构与工程：
  叙事结构只留一套口径——「五幕」是粗粒度骨架，「八段」是细分刻度，`references/pacing-spec.md`
  给出五幕 ↔ 八段对照表（旧版「七段」与那张 8 行的表不符，已改掉）；新增根目录 `smoke_test.py`
  全链冒烟（示例 spec → 渲染 → `audit.py` → `strip_chrome.py` → 转场，附字体回退与豆腐块检测）；
  `render.py` 拆成 `kit_common` / `kit_chrome` / `kit_forms` / `kit_scene` / `kit_film` 五个子模块，
  `render.py` 只剩 CLI 与 spec 加载——命令行、spec 格式、画面输出逐字节不变。
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
