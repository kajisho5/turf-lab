# -*- coding: utf-8 -*-
"""sitemap.php が読む静的URL一覧（php/sitemap_urls.php）を PUBLIC_MAP から作る。

★なぜ自動生成にするのか★
  sitemap.php の $urls は手書きの配列だった。ページを新しく作るたびに
  ここへ足す必要があるが、実際には足し忘れる。2026-07-28に調べたところ
  **公開している37ページがsitemapに載っていなかった**
  （/db/combo/ /db/trainer-homeaway/ /data/waku/ など、
  時間をかけて作った検証ページがまるごと漏れていた）。
  クローラーから見えなければ、作った意味がない。

  PUBLIC_MAP が本番に何を置くかの唯一の正なので、そこから機械的に作る。

出力: php/sitemap_urls.php （sitemap.php が require する）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deploy as D                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "php", "sitemap_urls.php")

# 更新頻度と優先度。前方一致で最初に当たったものを使う。
RULES = [
    ("/", "hourly", "1.0"),                # トップ（完全一致で後述）
    ("/record/", "daily", "0.9"),
    ("/ai/", "weekly", "0.9"),
    ("/articles/", "weekly", "0.9"),
    ("/data/jusho/", "weekly", "0.9"),
    ("/data/memo/", "weekly", "0.8"),
    ("/calendar/", "weekly", "0.8"),
    ("/db/", "weekly", "0.8"),
    ("/data/", "monthly", "0.8"),
    ("/about/", "monthly", "0.5"),
    ("/privacy/", "yearly", "0.3"),
]

# 出さないもの（noindex・運用者用・当日ごとに中身が変わる素通しページ）
SKIP = {"/race.html"}


def rule_for(u):
    if u == "/":
        return "hourly", "1.0"
    for prefix, freq, pri in RULES:
        if prefix != "/" and u.startswith(prefix):
            return freq, pri
    return "monthly", "0.6"


def main():
    urls = []
    for src, dst in D.PUBLIC_MAP:
        if not src.endswith(".html") or not os.path.exists(src):
            continue
        u = dst.replace("/kajikeiba.com", "")
        if u == "/index.html":
            u = "/"
        elif u.endswith("/index.html"):
            u = u[: -len("index.html")]
        if u in SKIP:
            continue
        # noindex を付けているページは sitemap に出さない（矛盾した指示になる）
        if "noindex" in open(src, encoding="utf-8", errors="replace").read():
            continue
        freq, pri = rule_for(u)
        urls.append((u, freq, pri))

    urls.sort(key=lambda x: (-float(x[2]), x[0]))
    body = "".join(
        f"  ['https://kajikeiba.com{u}', '{f}', '{p}'],\n" for u, f, p in urls)
    php = f"""<?php
/* 自動生成: backtest/gen_sitemap_urls.py
   ★手で編集しないこと★ PUBLIC_MAP を直してから再生成する。
   ページを作っても sitemap に足し忘れる事故を防ぐために機械生成にしている。 */
return [
{body}];
"""
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(php)
    print(f"生成: {OUT}  {len(urls)}件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
