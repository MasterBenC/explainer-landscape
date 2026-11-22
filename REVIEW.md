# explainer-landscape 代码审查（v0.3.1）

> 审查日期：2026-11-22 ｜ HEAD `e24fe06`（`feat(v0.3.1): 五幕/八段口径归一、新增全链 smoke_test.py、render.py 拆成五个子模块`）
> 已读：README.md、SKILL.md、meta.yaml、install.py、smoke_test.py、`assets/kit/` 全部 7 个脚本
> （render / audit / kit_common / kit_chrome / kit_forms / kit_scene / kit_film / strip_chrome）、
> `assets/examples/make_media.py`、两份示例 spec、`references/` 全部 10 份
> 未读：`assets/examples/media/*.png`、`assets/examples/out/*.png`（二进制）、kit_common 与 kit_forms 非关键段落（grep 核对）
> 结论只覆盖已读文件。

**本机实跑结论**：`python smoke_test.py` → 退出码 0，19 项通过 / 0 项失败（Pillow 13 + ffmpeg + Noto CJK）。
五幕/八段口径归一（`3+15+45+27+10=100`、`3+5+6+4+45+17+10+10=100`）与子模块拆分的参数一致性都对得上，
这两处 v0.3.1 改动本身是干净的。

但**验收脚本自身有一类系统性问题**：参数拼错、截图缺失、什么都没渲出来，三者都会**退出 0**。
冒烟测试全绿并不能证明链路可靠，因为它用的都是正确命令和齐全截图。

优先级：P0 = 会静默出错（验收假通过 / 用户数据被删）；P1 = 文档承诺与行为不符；P2 = 小问题清理。

---

## P0

### 1. `audit.py` 手工解析参数，拼错的 flag 被静默忽略，`--images` 缺值降级为"不检查"

`assets/kit/audit.py:449-454`：

```python
    rest = argv[2:]
    strict = "--strict" in rest
    img_dir = None
    if "--images" in rest:
        k = rest.index("--images")
        img_dir = rest[k + 1] if len(rest) > k + 1 else None
```

没有 argparse，未识别的参数被完全丢弃；`--images` 写在最后（后面没值）时 `img_dir = None`，像素检查整段跳过。
退出码只看 `assets/kit/audit.py:466-468`：

```python
    if fails or (strict and warns):
        return 1
    return 0
```

**我本机实测**：

| 命令 | 结果 |
|---|---|
| `audit.py spec.sample.json --image out/`（`--images` 拼成 `--image`） | `EXIT=0`，`9 镜 / 48.5s / FAIL 0 / WARN 0` —— 像素检查一次没跑 |
| `audit.py spec.sample.json --images`（无值） | `EXIT=0`（同上） |

作者以为做了"红占比 / 填充率 / 亮度"验收，实际只跑了字段检查，且退出码 0 表示通过。
**修复**：改 argparse，显式声明 `--strict` / `--images`（后者 `nargs=1` 必填值）；未知 flag 打印 ERROR 并 `return 2`。

### 2. `audit.py --images` 找不到图时只 WARN 并跳过，整批截图缺失也退出 0

`assets/kit/audit.py:416-418`：

```python
        if not os.path.exists(path):
            warn(f"{sid}: 没有渲染图 {path}，跳过像素检查")
            continue
```

`img_dir` 本身是否存在没有校验。**我本机实测**：`audit.py spec.sample.json --images nope/`（不存在的目录）
→ `FAIL 0 / WARN 9`，`EXIT=0`。加 `--strict` 才变 1。

即"什么都没检查到"= 通过。**修复**：`img_dir` 用 `os.path.isdir` 检查并记 FAIL；渲染图缺失记 FAIL（而非 WARN）。

### 3. `render.py` 未知 flag、或只给 `--only` 时，什么都不渲却退出 0

`assets/kit/render.py:67-69`：

```python
    flags = set(a for a in argv[3:] if a.startswith("--"))
    if not flags:
        flags = {"--png"}
```

只要出现任意 `--xx` 就不再走默认 `--png`，而未知 flag 不匹配任何 `if` 分支，直接落到末尾：

```python
    print(f"总时长 {spec_duration(spec):.1f}s / {len(spec['scenes'])} 镜")
    return 0
```

**我本机实测**：

| 命令 | 结果 |
|---|---|
| `render.py spec.json out/ --jpgs`（`--png` 拼错） | `EXIT=0`，输出目录 **0 个文件** |
| `render.py spec.json out/ --only s01`（只给 --only，没给输出 flag） | `EXIT=0`，输出目录 **0 个文件** |

**修复**：渲染结束检查"至少一个输出分支执行过"，没有则 `return 1`；未知 flag 显式报错。

### 4. `install.py` 静默覆盖用户改过的文件、并删除源目录里没有的文件

`install.py:58-64`：

```python
        if not same_file(s, d):
            shutil.copy2(s, d)
            copied += 1
    for rel in rel_files(dst):
        if rel not in src_files:
            os.remove(os.path.join(dst, rel))
            removed += 1
```

docstring 说"比先 rmtree 再 copytree 稳：删一半失败也不会毁掉旧版本"——对**升级**成立，但对**用户改动**效果等同于 rmtree：
用户在已装 skill 里改的 `SKILL.md`、自己加的 spec 会被覆盖或删除，无备份、无 `--dry-run`、无确认。
`--link` 分支更直接：`install.py:86-87` 对已存在目录 `shutil.rmtree(dst)`。

**修复**：内容不同时默认跳过并警告（列出差异文件名），`--force` 才覆盖/删除；`--force` 前先备份 `.bak`。

---

## P1

### 5. `strip_chrome.py` 读 spec 用 `utf-8`，BOM 直接崩，与 SKILL.md 承诺相反

- `SKILL.md:32`：`spec 存 UTF-8 即可；Windows 记事本写的 BOM 也能读（utf-8-sig）。`
- `assets/kit/strip_chrome.py:71`：`spec = json.loads(src.read_text(encoding="utf-8"))`
- 同链路的 `render.py:64`、`audit.py:455` 都是 `utf-8-sig`

Windows 记事本存过的 spec 跑切档必崩在 `json.loads`（`Unexpected UTF-8 BOM`），且不是友好提示。
**修复**：`strip_chrome.py:71` 改 `encoding="utf-8-sig"`。

### 6. `--video` 无视 `--only`：要重渲一镜，渲了全片

`render.py:109-116` 里 `--video` 分支调 `render_film(spec, ...)`，而 `kit_film.py:89` 用的是 `spec["scenes"]` 全量；
`--png` / `--mp4` 分支用的才是 `render.py:83` 的 `sel`。

**我本机实测**：`render.py spec.json out/ --video out/f.mp4 --only s01` → `EXIT=0`，ffprobe 时长 **48.5s**（整片），
而 s01 本身只有 1.5s。`render.py:11` 与 `references/cases-2026-11.md:27` 都承诺 `--only` 未列出的镜不写盘。

**修复**：`render_film` 接受场景子集，`--video` 时传入 `sel`。

### 7. smoke_test 的 audit 步骤注释承诺"不能有残留 WARN"，但没加 `--strict`

`smoke_test.py:221`：`if run([... AUDIT, minimal], "极简档 audit") is None:     # 撤干净后不能有残留 WARN`
而 WARN 永远不导致失败（见 P0-1）。切档残留恰好是以 WARN 形式报的（`audit.py:225-231`）。
冒烟测试另有字段级兜底（`smoke_test.py:206-215`），风险有限，但注释的保证不成立。
**修复**：该步加 `--strict`，或删掉误导性注释。

### 8. 文档声称机器可查"章节数 3–5"，audit 只查"<2 且 ≥12 镜"

- `references/pacing-spec.md:62`：`全片 3–5 个章节…`
- `assets/kit/audit.py:382`：`if len(scenes) >= 12 and len(uniq) < 2:` → `warn("只有一个章节，4 分钟片建议 3–5 个")`
- `references/qa-checklist.md` 把"章节数 3–5 个"标为机器可查 ✓

上下界都没查。**修复**：改成 3–5 区间检查，或把 qa-checklist 的 ✓ 去掉。

### 9. `callouts` 写了但没写对应 `motion` 条目时静默不画

- `assets/kit/kit_chrome.py:117`：`p = ease_out(P(mm, f"callout[{i}]", t, 0.0))`，缺省 `0.0` → 下一行 `if p <= 0.001: continue`
- `kit_common.py:377-439` 的 `auto_motion` 从不生成 `callout[i]` 条目
- `references/depth-and-texture.md:60-62` 的示例只写 `callouts`、不写 `motion`

按文档示例写，标注一个都不会出现，`audit.py:328-341` 也只查 x/y/text，不查这种"绑空"——而这正是 `audit.py`
docstring 自称要抓的场景，只是漏了 callouts。
**修复**：`auto_motion` 为 callouts 补默认入场时间；或 audit 对"有 callouts 无对应 motion"记 FAIL；或文档写明必须配 motion。

---

## P2

| # | 位置 | 问题 |
|---|---|---|
| 10 | `render.py:20` | docstring 写"实现分在**四个**子模块"，下面列了五个 |
| 11 | `smoke_test.py:11` | 写"**四步**各查什么"，实际列 1–5 共五步 |
| 12 | `kit_film.py:17` / `kit_scene.py:24` / `kit_film.py:93` | `dur` 默认值三处不一致：总时长按 4、静帧按 6、`render_film` 直接 `sc["dur"]` 缺则 KeyError（`spec-schema.md:21` 定 4） |
| 13 | `audit.py:358-361` | `if not 4 <= spm <= 14: warn(...)` 接 `elif spm < 8: warn("偏慢")`——4–8 既在合规区间又被提示偏慢 |
| 14 | `audit.py:22` | `MARGIN, RIGHT = 134, 1786` 全文未被引用（死代码） |
| 15 | `assets/examples/make_media.py:78-79` | 打印路径用 Windows 反斜杠，Linux 下显示成 `.../media\doc-page.png` |
| 16 | `references/layout-spec.md:91-99` | 栅格自相矛盾：`12 栏 × 120 + 11 × 16 = 1616`，而内容宽是 1652；"左 1–6 栏 134–866"按此栅格算应是 134–934 |
| 17 | `references/layout-spec.md:65` vs `:37` | H2 行把"章节牌"写成 64，chrome 表与代码（`kit_chrome.py:29/35`）都是 60 |
| 18 | `SKILL.md:114` vs `references/form-catalog.md:91` | list 条目 `at` 字段：一处说"每条带 at"，一处说"渲染器不读 at" |
| 19 | `README.md:12` | 只写"Python ≥ 3.9、Pillow"，而 `kit_common.py:87` 的 `ImageFont.load_default(size)` 需要 Pillow ≥ 10.1，旧版会 TypeError |

---

## 修复顺序

1. **验收脚本先能失败**（P0-1、P0-2、P0-3）：audit/render 改 argparse，未知 flag 报错、缺图记 FAIL、渲染无产出报错
2. `install.py` 默认不覆盖/不删除用户文件，`--force` 才动并有 `.bak`（P0-4）
3. `--video` 尊重 `--only`；`strip_chrome` 读 BOM（P1-6、P1-5）
4. smoke_test 的 audit 步骤加 `--strict`（P1-7）
5. 文档与代码口径对齐：章节数检查（P1-8）、callouts 绑定（P1-9）、栅格/字号/`at`/`dur` 默认值（P2-12、P2-16、P2-17、P2-18）
6. 清死代码与注释数字（P2-10、P2-11、P2-14、P2-15）
