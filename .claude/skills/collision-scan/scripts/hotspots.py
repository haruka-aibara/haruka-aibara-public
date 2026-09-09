#!/usr/bin/env python3
"""git 履歴から「ぶつかりやすい場所」の証拠を集める。

出すのは3つ。どれも履歴という事実に基づく。
  1. churn  : 変更回数と、そのうち修正系コミット（fix/revert/hotfix 等）の割合
  2. authors: 著者の集中度（1人しか触っていない = 質問先が1人）
  3. cochange: 指定パスと同時に変更されがちなファイル（言われないと気づけない依存）

使い方:
  python3 hotspots.py --since 1.year                    # リポジトリ全体の上位
  python3 hotspots.py --since 2.years path/a.py path/b  # 指定パスに絞る + 共変更相手
"""
import argparse
import collections
import subprocess
import sys

FIX_WORDS = ("fix", "revert", "hotfix", "bug", "patch", "修正", "不具合", "障害", "戻し")


def git(args):
    r = subprocess.run(["git"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"git {' '.join(args)} が失敗しました:\n{r.stderr.strip()}")
    return r.stdout


def commits(since):
    """[(subject, [files]), ...] を新しい順に返す。"""
    out = git(["log", f"--since={since}", "--no-merges",
               "--format=%x00%s", "--name-only"])
    result = []
    for block in out.split("\x00"):
        block = block.strip("\n")
        if not block:
            continue
        lines = block.split("\n")
        subject, files = lines[0], [f for f in lines[1:] if f.strip()]
        if files:
            result.append((subject, files))
    return result


def is_fix(subject):
    s = subject.lower()
    return any(w in s for w in FIX_WORDS)


def under(path, targets):
    return not targets or any(path == t or path.startswith(t.rstrip("/") + "/") for t in targets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="調べたいファイル・ディレクトリ（省略すると全体）")
    ap.add_argument("--since", default="1.year", help="git log --since に渡す期間（既定: 1.year）")
    ap.add_argument("--top", type=int, default=15, help="表示件数（既定: 15）")
    args = ap.parse_args()

    log = commits(args.since)
    if not log:
        sys.exit(f"直近 {args.since} にコミットがありません。--since を広げてください。")

    churn = collections.Counter()
    fixes = collections.Counter()
    for subject, files in log:
        fix = is_fix(subject)
        for f in files:
            churn[f] += 1
            if fix:
                fixes[f] += 1

    targets = [p.rstrip("/") for p in args.paths]
    print(f"# 期間: 直近 {args.since} / 対象コミット {len(log)} 件\n")

    print("## 変更が多い場所（修正系コミットの割合つき）")
    print("修正系の割合が高いほど、これまで繰り返し燃えてきた場所。\n")
    rows = [(f, c) for f, c in churn.most_common() if under(f, targets)][: args.top]
    if not rows:
        print("該当なし\n")
    for f, c in rows:
        fx = fixes[f]
        share = f"{fx / c:.0%}" if c else "-"
        print(f"- {f} — 変更 {c} 回 / うち修正系 {fx} 回（{share}）")
    print()

    print("## 著者の集中度")
    print("1人しか触っていない場所は、詰まったときの質問先が1人しかいない。\n")
    for f, _ in rows:
        # git shortlog は範囲を渡さないと stdin を読みに行って止まるので log で数える
        out = git(["log", "--no-merges", f"--since={args.since}", "--format=%an", "--", f])
        who = collections.Counter(l.strip() for l in out.split("\n") if l.strip())
        if not who:
            continue
        name, cnt = who.most_common(1)[0]
        mark = "  ← 1人だけ" if len(who) == 1 else ""
        print(f"- {f} — {len(who)}人 / 最多 {name}（{cnt} 回）{mark}")
    print()

    if targets:
        print("## 同時に変更されがちなファイル")
        print("指定したパスと一緒に直す羽目になりやすい相手。事前に見落としやすい依存。\n")
        for t in targets:
            partners = collections.Counter()
            base = 0
            for _, files in log:
                touched = [f for f in files if under(f, [t])]
                if not touched:
                    continue
                base += 1
                for f in files:
                    if not under(f, [t]):
                        partners[f] += 1
            if base == 0:
                print(f"### {t}\n該当コミットなし\n")
                continue
            print(f"### {t}（変更されたコミット {base} 件）")
            shown = [(f, c) for f, c in partners.most_common(8) if c >= 2]
            if not shown:
                print("同時変更の目立つ相手なし\n")
                continue
            for f, c in shown:
                print(f"- {f} — {c}/{base} 回（{c / base:.0%}）同時に変更")
            print()


if __name__ == "__main__":
    main()
