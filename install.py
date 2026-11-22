#!/usr/bin/env python3
"""把 explainer-landscape 安装到各 agent 的 skills 目录。

    python install.py                      # 自动找 ~/.agents/skills、~/.claude/skills、~/.codex/skills
    python install.py --target PATH        # 只装到一个目录
    python install.py --link               # 用符号链接（改源即生效，需权限）
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

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


def sync_tree(src: str, dst: str) -> tuple[int, int]:
    """就地覆盖 + 清理多余文件。比先 rmtree 再 copytree 稳：删一半失败也不会毁掉旧版本。"""
    src_files = set(rel_files(src))
    copied = removed = 0
    for rel in sorted(src_files):
        s = os.path.join(src, rel)
        d = os.path.join(dst, rel)
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if not same_file(s, d):
            shutil.copy2(s, d)
            copied += 1
    for rel in rel_files(dst):
        if rel not in src_files:
            os.remove(os.path.join(dst, rel))
            removed += 1
    return copied, removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="append")
    ap.add_argument("--link", action="store_true")
    args = ap.parse_args()

    src = os.path.dirname(os.path.abspath(__file__))
    targets = args.target or default_targets()
    if not targets:
        print("没找到 skills 目录，用 --target 指定")
        return 1

    name = SKILL_NAME
    for t in targets:
        t = os.path.expanduser(t)
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
            if os.path.islink(dst) or os.path.exists(dst):
                if os.path.islink(dst):
                    os.remove(dst)
                else:
                    print(f"  {dst} 是实体目录，先删掉再软链（内容会丢）")
                    shutil.rmtree(dst)
            os.symlink(src, dst, target_is_directory=True)
            print(f"link {dst} -> {src}")
        else:
            copied, removed = sync_tree(src, dst)
            print(f"sync {dst}  (updated {copied}, removed {removed})")
    print("装好了。重启 agent 会话后生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
