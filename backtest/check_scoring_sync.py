# -*- coding: utf-8 -*-
"""deploy/tweet.html が core/scoring.js の採点ロジックを二重管理していないか確認する

★なぜ要るか★
  deploy/tweet.html は core/scoring.js を <script src> で読み込んでおらず、
  fundamentalScore/gbmScore/speedIndex/factorW/parseShutuba 等18関数と
  RL_STD・EXT・GBM_MODEL（267,952バイト）を自前でコピーして持っている。
  2026-07-19 に kochi.html へ関数をコピーした際、写し忘れでv357/359/360/364と
  4回連鎖して本番が壊れた前例がある（同じ「コピーの同期漏れ」という病気）。
  tweet.html自身がcore/scoring.jsに対して同じ二重管理状態にあるため、
  片方だけ直して他方を直し忘れるリスクが常にある。

  本格的な統合（tweet.htmlをscript src読み込みに変える）は
  3サイトへのパス解決・読み込み順序・sw.jsキャッシュ対象など壊れる要素が多く
  リスクが大きい。統合の代わりに「ズレたら気づく」チェックだけをここで機械化する。

  ★2026-07-24時点では全項目バイト単位で完全一致（ハッシュ比較済み）★
  このチェックは「今後の変更でズレが出た時に検知する」ためのもの。

使い方:
  python backtest/check_scoring_sync.py
  終了コード: 0=完全一致 / 1=ズレあり（tweet.htmlとcore/scoring.jsの片方だけ直した）
"""
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TWEET = os.path.join(ROOT, "deploy", "tweet.html")
SCORING = os.path.join(ROOT, "core", "scoring.js")


def extract_script(path):
    text = open(path, encoding="utf-8").read()
    blocks = re.findall(r"<script>([\s\S]*?)</script>", text)
    return "\n".join(blocks) if blocks else text


def balanced_span(src, start_idx, open_ch, close_ch):
    depth = 0
    i = start_idx
    while i < len(src):
        if src[i] == open_ch:
            depth += 1
        elif src[i] == close_ch:
            depth -= 1
            if depth == 0:
                return src[start_idx:i + 1]
        i += 1
    return None


def extract_function(src, name):
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\(", src)
    if not m:
        return None
    brace = src.index("{", m.end())
    body = balanced_span(src, brace, "{", "}")
    return None if body is None else src[m.start():brace] + body


def extract_const(src, name):
    m = re.search(r"const\s+" + re.escape(name) + r"\s*=\s*", src)
    if not m:
        return None
    i = m.end()
    if i >= len(src) or src[i] not in "{[":
        return None
    body = balanced_span(src, i, src[i], "}" if src[i] == "{" else "]")
    return None if body is None else src[m.start():i] + body


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def sha1(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def main():
    if not (os.path.exists(TWEET) and os.path.exists(SCORING)):
        print("deploy/tweet.html または core/scoring.js が見つからない")
        return 1

    tweet_js = extract_script(TWEET)
    scoring_js = open(SCORING, encoding="utf-8").read()

    func_names = sorted(set(re.findall(r"^function\s+([A-Za-z0-9_]+)\s*\(",
                                        scoring_js, re.MULTILINE)))
    const_names = sorted(set(re.findall(r"^const\s+([A-Za-z0-9_]+)\s*=",
                                         scoring_js, re.MULTILINE)))

    mismatches = []
    checked = 0
    for name in func_names:
        a = extract_function(tweet_js, name)
        b = extract_function(scoring_js, name)
        if a is None:
            continue   # tweet.html側で使っていない関数（core/race_app.js専用）は対象外
        checked += 1
        if norm(a) != norm(b):
            mismatches.append(("function", name, len(a), len(b)))

    for name in const_names:
        a = extract_const(tweet_js, name)
        b = extract_const(scoring_js, name)
        if a is None:
            continue
        checked += 1
        if a != b:
            mismatches.append(("const", name, len(a), len(b)))

    if not mismatches:
        print(f"OK  {checked}件、tweet.html と core/scoring.js は完全一致")
        return 0

    print(f"★ズレ検出★ {len(mismatches)}/{checked}件が不一致\n")
    for kind, name, la, lb in mismatches:
        print(f"  [{kind}] {name}  tweet.html={la}B (sha1={sha1(name)})  "
              f"scoring.js={lb}B")
    print("\ndeploy/tweet.html と core/scoring.js の該当箇所を突き合わせて"
          "どちらが正か確認し、両方を同じ内容に揃えること。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
