#!/usr/bin/env python3
"""把 explainer-landscape 安装到各 agent 的 skills 目录。

    python install.py                      # 自动找 ~/.agents/skills、~/.claude/skills、~/.codex/skills
    python install.py --target PATH        # 只装到一个目录
    python install.py --link               # 用符号链接（改源即生效，需权限）
    python install.py --dry-run            # 只打印会做什么，一个文件都不动
    python install.py --force              # 覆盖内容不同的文件 / 删除源里没有的文件（动前先备份 .bak）

默认是**安全模式**：已装目录里你自己改过的 `SKILL.md`、自己加的 spec，内容与源不同就
**跳过并警告**（列出差异文件名），不覆盖、不删除；源目录里已删掉的文件也不会去 dst 里删。
要真的同步成和源一样，显式加 `--force`——那时每个被覆盖 / 被删除的文件先生成 `.bak`。

`--link` 的目标已存在且非空时同样要 `--force`；`--force` 下旧目录被改名成 `<name>.bak`
（而不是 rmtree），以便回滚。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

SKIP = {"__pycache__", ".git", "out"}

# 目标目录名固定，不跟着源码目录名走：从 GitHub zip 解出来的目录常叫
# explainer-landscape-main（或带 -0.3.2 后缀），跟着走会在 skills 里留一堆版本尾巴，
# agent 侧按名字找 skill 时就找不到。源目录名再乱，装进去的始终是 explainer-landscape。
SKILL_NAME = "explainer-landscape"


def _same(a: str, b: str) -> bool:
    return os.path.realpath(a) == os.path.realpath(b)


def _nested(a: str, b: str) -> bool:
    ra, rb = os.path.realpath(a), os.path.realpath(b)
    return ra.startswith(rb + os.sep) or rb.startswith(ra + os.sep)


def default_targets() -> list[str]:
    home = os.path.expanduser("~")
    names = [".agents/skills", ".claude/skills", ".codex/skills"]
    found = [os.path.join(home, n) for n in names
             if os.path.isdir(os.path.join(home, os.path.dirname(n))) or os.path.isdir(os.path.join(home, n))]
    if found:
        return found
    # 全新机器上一个 agent 目录都没有：不能静默返回空列表什么都不装。
    # 回退到通用 Agents 技能目录（DSH / 豆包 / Trae 都读这里），并打印说明。
    fallback = os.path.join(home, ".agents", "skills")
    print(f"没找到任何已有 skills 目录，回退创建 {fallback}")
    return [fallback]


def rel_files(root: str) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for f in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, f), root))
    return out


def same_file(a: str, b: str) -> bool:
    if not os.path.exists(b) or os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def plan_sync(src: str, dst: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """算出 (新增, 内容不同, 相同, dst 多出) 四组相对路径，不落盘。"""
    src_files = set(rel_files(src))
    dst_files = set(rel_files(dst)) if os.path.isdir(dst) else set()
    new, changed, same = [], [], []
    for rel in sorted(src_files):
        if rel not in dst_files:
            new.append(rel)
        elif same_file(os.path.join(src, rel), os.path.join(dst, rel)):
            same.append(rel)
        else:
            changed.append(rel)
    return new, changed, same, sorted(dst_files - src_files)


def _backup(path: str) -> str:
    """覆盖 / 删除前留一份 .bak（已有 .bak 就带时间戳，不互相顶掉）。"""
    bak = path + ".bak"
    if os.path.exists(bak):
        bak = f"{path}.bak.{int(time.time())}"
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.copytree(path, bak)
    elif os.path.islink(path) or not os.path.exists(path):
        pass                                   # 符号链接不留备份，记下即可
    else:
        shutil.copy2(path, bak)
    return bak


def sync_tree(src: str, dst: str, force: bool, dry_run: bool) -> tuple[int, int, list[str]]:
    """安全同步：内容不同默认跳过并警告；`--force` 才覆盖 / 删除，且动前写 .bak。

    返回 (写入数, 删除数, 差异文件名列表)。
    """
    new, changed, same, extra = plan_sync(src, dst)
    diffs = changed + extra
    wrote = removed = 0

    for rel in new + changed:
        s, d = os.path.join(src, rel), os.path.join(dst, rel)
        if rel in changed and not force:
            continue                                  # 安全模式：不覆盖用户改动
        if os.path.isdir(d) and not os.path.islink(d):
            # 源里是文件、目标里同名的却是个目录：不能直接 copy2，安全模式下跳过
            if not force:
                print(f"    警告：{rel} 在已装目录里是个目录（源里是文件），跳过；--force 会把它改名 .bak")
                continue
            if dry_run:
                print(f"    目录 {rel} 改名 .bak 后写入文件")
                wrote += 1
                continue
            bak = _backup(d)
            shutil.rmtree(d)
            print(f"    目录 {rel} 改名 -> {os.path.basename(bak)}")
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
            wrote += 1
            continue
        if dry_run:
            print(f"    {'覆盖' if rel in changed else '新增'} {rel}"
                  + ("（先备份 .bak）" if rel in changed else ""))
            wrote += 1
            continue
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if rel in changed:
            bak = _backup(d)
            print(f"    覆盖 {rel}（旧文件 -> {os.path.basename(bak)}）")
        shutil.copy2(s, d)
        wrote += 1

    for rel in extra:
        d = os.path.join(dst, rel)
        if not force:
            continue                                  # 安全模式：不删源里没有的文件
        if dry_run:
            print(f"    删除 {rel}（改名成 .bak）")
            removed += 1
            continue
        bak = _backup(d) if os.path.exists(d) else None
        if os.path.exists(d):
            os.remove(d)
        print(f"    删除 {rel}" + (f"（原名保留为 {os.path.basename(bak)}）" if bak else ""))
        removed += 1

    return wrote, removed, diffs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="append")
    ap.add_argument("--link", action="store_true", help="符号链接安装（改源即生效）")
    ap.add_argument("--force", action="store_true",
                    help="覆盖内容不同的文件 / 删除源里没有的文件（动前备份 .bak）；--link 目标非空时也要求它")
    ap.add_argument("--dry-run", action="store_true", help="只打印会做什么，不动任何文件")
    args = ap.parse_args()

    src = os.path.dirname(os.path.abspath(__file__))
    targets = args.target or default_targets()
    if not targets:
        print("没找到 skills 目录，用 --target 指定")
        return 1

    name = SKILL_NAME
    for t in targets:
        t = os.path.expanduser(t)
        if not args.dry_run:
            os.makedirs(t, exist_ok=True)
        dst = os.path.join(t, name)
        # 已经站在安装位里跑 install.py（很常见：装过一次之后又从 skill 目录跑一遍），
        # dst 就是 src 本身。这时 sync_tree/rmtree 会把源码当「多余文件」删掉——直接跳过。
        if _same(src, dst):
            print(f"跳过 {dst}：这就是源码目录本身，再同步会把源码删掉")
            continue
        if _nested(src, dst):
            print(f"跳过 {dst}：目标和源码目录互相嵌套（{src} / {dst}），先手动挪开")
            continue
        if args.link:
            exists = os.path.islink(dst) or os.path.exists(dst)
            if exists and not args.force:
                print(f"跳过 {dst}：目标已存在（--link 会替换它），确认要换就加 --force")
                continue
            if args.dry_run:
                print(f"    link {dst} -> {src}" + ("（旧目标改名 .bak）" if exists else ""))
                continue
            if exists:
                bak = f"{dst}.bak" if not os.path.exists(f"{dst}.bak") else f"{dst}.bak.{int(time.time())}"
                if os.path.islink(dst):
                    os.remove(dst)          # 符号链接本身不留备份（指向的源目录没动）
                else:
                    os.replace(dst, bak)    # 真目录/文件改名，而不是 rmtree
                    print(f"    旧目标改名 -> {os.path.basename(bak)}")
            os.symlink(src, dst, target_is_directory=True)
            print(f"link {dst} -> {src}")
        else:
            wrote, removed, diffs = sync_tree(src, dst, args.force, args.dry_run)
            tag = "（dry-run，未落盘）" if args.dry_run else ""
            print(f"sync {dst}  (written {wrote}, removed {removed}){tag}")
            if diffs and not args.force:
                print(f"    警告：{len(diffs)} 个文件与已装版本不同，已跳过（不覆盖、不删除）：")
                for rel in diffs[:20]:
                    print(f"      - {rel}")
                if len(diffs) > 20:
                    print(f"      … 另有 {len(diffs) - 20} 个")
                print("    确认要同步成源目录的样子就加 --force（会先写 .bak）")
    print("装好了。重启 agent 会话后生效。" if not args.dry_run else "dry-run 结束：没有改动任何文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
