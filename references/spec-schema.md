# spec 字段全表（`render.py` 实际读取的键）

这份表以代码为准，不是设计意图。写 spec 时**只抄这里的键名**——旧文档里出现过的
`easing` / `kind` / `num` / `axis` / 槽位 `at` 都不生效，写了不报错但也不会有任何效果。

## 顶层

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `canvas` | object | — | `{"w": 1920, "h": 1080, "fps": 30}`；`w/h` 固定 1920×1080；`fps` 缺省按 30 兜底 |
| `title` | string | — | 只给人看（渲染器不读） |
| `brand` | string | — | 全局品牌词；**只画在有 `chapter` 的镜头上**，极简档要删 |
| `scenes` | array | — | 必填，至少一镜 |
| `chrome` | string | — | `full` / `minimal` / `bare`。渲染器不读，`strip_chrome.py` 写入、`audit.py` 用它判断极简档规则 |

## 场景公共字段

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `id` | string | — | **必填**。输出文件名 `{id}.png`、颗粒种子、`fg` 缓存键 |
| `dur` | number | 4 | 本镜秒数。`--video` 的总时长 = Σdur |
| `form` | string | — | **必填**：`bignum` / `evidence` / `list` / `timeline` / `relation` / `sources` / `chart` / `photo` |
| `t` | number | — | 只给人看的时间轴刻度；`audit.py` 会检查它和 Σdur 是否一致 |
| `transition` | object | `{"type":"cut"}` | `{"type": ..., "duration": ...}`，见下 |
| `depth` | string | `bg` | `bg` 图铺满 / `fg` 档案卡浮起 / `split` 左文右图 |
| `bg` | path | — | 背景图（相对 spec 文件解析）。`depth` 三档都靠它 |
| `blur` | number | 0 | 背景高斯模糊半径（`bg` 档） |
| `scrim` | number \| [number, number] | `[0.0, 0.72]` | 整体压暗强度（第二个值）；`bg` 档生效 |
| `split_x` | number | 0.42 | `split` 档的分栏位置（占宽比例） |
| `crop` | object | `{zoom:1.10, cx:0.5, cy:0.5}` | `split` 档右侧图的裁切 |
| `archival` | object | `{desat:0.62, warm:1.0, dark:0.0}` | 只作用在图片层（去饱和 / 暖调 / 压暗）+ 固定颗粒 |
| `camera` | number | **0（关）** | 全幅微推幅度，推荐 `0.010–0.012`，上限 0.02；纯排版镜别开 |
| `chapter` | string | — | 章节牌（60px）；`线索一·爆料的媒体` 里的 `·` 会分色 |
| `brand` | string | 继承顶层 | 章节牌右侧品牌词；**没有 `chapter` 就不画** |
| `label_left` | string | — | 左上角账号/栏目标签 + 红线 |
| `label_right` | string | — | 右上角标记 |
| `when` | string | — | 日期戳（40px，y=176） |
| `rel` | string | — | 相对时间（30px，y=248） |
| `title` | string | — | 主标题（64px，y=310，最多两行） |
| `title_w` | number | 900 | 主标题折行宽度 |
| `kicker` | string | — | 副标题 / 署名（28px，跟在标题下方） |
| `subtitle` | string | — | 底部字幕（54px，基线 y=1000，最多两行） |
| `source` | string | — | 来源行（21px，y=884）；**只给档案档**，太长的会往下压字幕 |
| `tc` | string | — | 时间码文本（`00:04.0`），要配 `show_tc` |
| `show_tc` | bool | false | 不写就不画时间码 |
| `disclaimer` | bool | **true** | 不写也会在 y=1012 画一行免责；极简档必须显式 `false` |
| `strap` | string | — | 下三分之一横条（34px，基线 y=812）；超过 ~24 字会被硬截 |
| `strap_tab` | string | — | 横条左侧强调色标签（要配 `strap`） |
| `clock` | string | — | 横条右端等宽时间戳（要配 `strap`，否则不画） |
| `callouts` | array | — | `[{x, y, dx, dy, text}]`；`x/y` 是 0–1 归一化坐标，`dx/dy` 是像素位移 |
| `motion` | array | — | `[{item, at, dur, ease}]`，见 `motion-spec.md` |
| `beats` | array | — | 元素出场时刻（秒，相对本镜）；只在**没写** `motion` 时生效 |
| `slots` | object | `{}` | 版式槽位，见下 |

### `transition`

| 键 | 默认 | 取值 |
|---|---|---|
| `type` | `cut` | `cut` / `fade` / `dissolve` / `wipe` / `blur`（`blur` 渲成黑场） |
| `duration` | 0 | 秒；必须 **小于本镜 `dur`**；常规 0.35–0.6 |

转场吃的是前一镜的尾部，`--video` 输出总时长不变。

## 八种版式的槽位

### `bignum` 巨数字卡

| 槽位 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `number` | ✅ | string | 数字本身；建议 `$2500万` 这样整串给，或数字 + `unit` |
| `unit` | — | string | 单独给单位，按 1/3 字号（56px）跟在数字后 |
| `caption` | 二选一 | string | 一句解释（42px） |
| `note` | 二选一 | string | 右下角出处（21px） |
| `emphasis` | — | bool | true 用强调红 |
| `count` | — | bool，默认 **false** | true 才做数字滚动（常规禁用） |

### `evidence` 双栏证据

| 槽位 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `left` | — | path | 左侧画面；缺省画占位框 |
| `right` | — | path | 右侧截图（建议给）；缺省画占位框 |
| `quote` | — | string | 引文（36px，y=780） |
| `attrib` | 有 quote 时必填 | string | 机构 · 日期（22px） |

### `list` 逐条揭示

| 槽位 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `items` | ✅ | array | `[{n, text}]`；`n` 缺省为 `01`… |
| `media` | — | path | 右侧配图（1180–1786 × 470–800） |

条目出现时间只看 `motion` / `beats`，条目里的 `at` 不读。

### `timeline` 时间轴对比

| 槽位 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `points` | ✅ | array | `[{label, value}]`，2–4 个 |
| `delta` | — | string | 两点之间的倍数/差值（64px，强调红） |

`axis` 不读。

### `relation` 关系图

| 槽位 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `center` | ✅ | string | 中心节点（≤8 字） |
| `satellites` | ✅ | array | `[{label}]`，3–5 个 |

`satellites` 里的 `kind` / `at` 不读；连线统一 `line` 细线，布局自动对称。

### `sources` 结尾来源清单

| 槽位 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `closing` | 建议 | string | 结语（88px，最多两行，y=380 起） |
| `blocks` | ✅ | array | `[{title, lines: [...]}]`；来源区 y=210 起，行距 34px |

**必须是最后一镜**；没有滚动实现，超过 ~18 行请精简或拆镜。

### `chart` 数据图

| 槽位 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `kind` | — | string，默认 `bar` | `bar` / `line` / `donut` / `kpi` |
| `data` | ✅ | array | `[{name, label, value, highlight?}]`；`kpi` 的 `value` 可直接给字符串 |
| `chart_title` | — | string | 图上方 60px 处的口径说明 |
| `source_note` | — | string | 右下角（1780, 860）的单位/出处 |

上限：bar 5 根 / line 6 点 / donut 5 段；`highlight` 一屏只能一个。

### `photo` 图片镜

| 槽位 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `image` | 视 `depth` | path | `depth` 为 `bg/fg/split` 时改用场景级 `bg`，这里不读 |
| `caption` | 建议 | string | 一句话说明 |
| `credit` | ✅（规范） | string | 图源机构 + 日期 |
| `framed` | — | bool | true = 右侧卡片（900–1786 × 300–800） |
| `scrim` | — | number，默认 0.46 | 整幅出血时顶部暗带占比 |

## 最容易踩的 10 个坑

1. `disclaimer` 默认 **true**：极简档不显式 `false` 就会多一行免责。
2. 顶层 `brand` 会画到每一镜，但**只在有 `chapter` 时**；极简档必须删。
3. `motion` 只认 `item` / `at` / `dur` / `ease`。`easing`、`kind` 无效。
4. `ease` 只认 `out` / `in_out` / `instant` / `linear`；`ease_out` 会静默变匀速。
5. 巨数字卡的 item 是 `number`，不是 `num`。
6. 写了**非空** `motion` 就不再自动排：没列进去的逐条元素**永远不会出现**（`"motion": []` 仍会走自动排布）。
7. 槽位里的 `at`（`items` / `points` / `satellites`）不读，用 `motion` 或 `beats`。
8. `slots.image` 在 `depth: bg/fg/split` 时被忽略，图要给 `bg`。
9. `clock` 没有 `strap` 就不画；`tc` 没有 `show_tc` 也不画。
10. `sources` 必须在最后；`transition.duration` 必须小于本镜 `dur`。

跑 `python "<skill-dir>/assets/kit/audit.py" spec.json`（有静帧加 `--images out/`）能抓掉上面 10 条里的 8 条。
