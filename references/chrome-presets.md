# chrome 两档：档案档 / 极简档

`render.py` 的常驻元素全部是**可选字段**：写了就画，不写就没有。所以「要不要角标」不是改代码，
是改 spec。实战里两档都跑过，2026-11 的结论是——**用户真实的选择是极简档**，而且不是一次就选对：
先嫌字多，全删之后又嫌「太单一」，最后才收敛到「只留必要的字」。

## 字段对照

| 字段 | 画什么 | 位置 | 档案档 | 极简档 |
|---|---|---|---|---|
| `label_left` | 左上角账号/栏目标签 + 红线 | (58, 34) | ✅ | ❌ |
| `label_right` | 右上角标记 | 右上 (W−58, 36) | ✅ | ❌ |
| `chapter` | 章节牌（60px 粗体，`·` 前后分色） | (134, 96) | ✅ 每 30–40 s 一次 | ✅ 保留（这是结构，不是角标） |
| `brand` | 章节牌右边的品牌词 | 右上 | ✅ | ❌ |
| `when` | 日期戳 | (134, 176) | ✅ | ❌ |
| `rel` | 相对时间（「两天前」） | (134, 248) | ✅ | ❌ |
| `subtitle` | 底部字幕（54px，最多两行） | 基线 y=1000 | ✅ | ✅（用户自己烧时留空） |
| `source` | 来源行（21px） | (134, 884) | ✅ | ❌ 收到片尾 `sources` 镜 |
| `tc` + `show_tc` | 右下时间码 | (RIGHT−40, 1006) | 可选 | ❌ |
| `disclaimer` | 「本视频引用的研究与数据均标注出处」 | (134, 1012) | 默认 true | **必须显式 false** |

注意 `disclaimer` 默认是 **true**：不写也会画一行免责声明。极简档一定要逐个场景写 `"disclaimer": false`，
或者直接用下面的脚本一次性关掉。

## 极简档示例场景

```json
{
  "id": "s05", "dur": 12.0, "form": "photo", "depth": "bg",
  "chapter": "线索一·5 万颗芯片",
  "subtitle": "库存单上少掉的这五万颗，才是这件事的引信",
  "disclaimer": false,
  "slots": {"image": "media/gb300.jpg", "caption": ""},
  "motion": [{"item": "caption", "at": 0.6, "kind": "appear", "easing": "out", "dur": 0.35}]
}
```

## 一条命令切档

```bash
# 全片切成极简档（保留 chapter，把 source/when/rel/tc/brand/disclaimer 全关掉）
python assets/kit/strip_chrome.py my_spec.json -o my_spec.minimal.json

# 连 chapter 一起关（只剩图 + 字幕）
python assets/kit/strip_chrome.py my_spec.json -o my_spec.bare.json --drop-chapter

# 反向：从极简档看还缺什么（只报告，不改文件）
python assets/kit/strip_chrome.py my_spec.json --check
```

脚本只改 chrome 字段，不动版式、槽位和 `motion`，所以切档前后**画面主体一模一样**，可以直接 A/B 对比。

## 什么时候不要极简

- 素材以截图为主、观众需要随时知道「这是哪天的哪家媒体」→ 档案档；
- 片子超过 8 分钟、章节多 → 极简档 + 更频繁的 `chapter`（章节牌是唯一保留的导航）；
- 发布到需要「来源可信度」的平台（调查类）→ 极简档 + 片尾 `sources` 镜写全。
