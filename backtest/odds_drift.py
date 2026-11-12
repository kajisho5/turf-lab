# -*- coding: utf-8 -*-
"""★発走までの残り時間ごとにオッズがどれだけ動くかを実測する★（2026-07-31）

なぜ要るか:
  LINE配信は「発走の約7分前」に送り、**その時点の複勝オッズ**で床（◎が3着内なら
  必ずプラス）を組んでいる。送信をもっと早めたい（投票締切まで余裕を作りたい）が、
  早めるほど締切までにオッズが動き、**床が割れる**可能性が上がる。
  「何分前なら床が守れるか」を勘で決めないための実測。

見るもの:
  oddslog に貯まった単勝オッズのスナップショット（mtp=発走までの残り分数つき）。
  ★複勝オッズは記録していない★ので単勝で代用する（両者は同じ方向に動く）。
  ◎の代わりに「最終的に1番人気だった馬」を追う（配信の◎はたいてい上位人気）。

出すもの:
  残り分数の帯ごとに、締切直前(mtp<=2)に対する**下振れ率**の分布。
  下振れ = オッズが下がる = 払戻が減る = 床が割れる方向。

使い方:
  python backtest/odds_drift.py 20260731 [20260801 ...]
  （日付を省略すると保存済みの全日付）
"""
import json
import statistics
import sys
import time
import urllib.request

BASE = "https://seventh-well.com/odds/oddslog.php"
BANDS = [(3, 5), (6, 8), (9, 12), (13, 20), (21, 40)]


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    dates = sys.argv[1:]
    if not dates:
        # action=dates は [{'date':'20260802','races':32},...] を返す（文字列ではない）
        dates = [d["date"] if isinstance(d, dict) else d
                 for d in get(f"{BASE}?action=dates").get("dates", [])]
    rows = {b: [] for b in BANDS}
    n_race = n_used = 0
    for d in dates:
        for rc in get(f"{BASE}?action=list&date={d}").get("races", []):
            n_race += 1
            time.sleep(0.15)          # WAF対策（連投で403になった前科）
            try:
                j = get(f"{BASE}?action=get&rid={rc['rid']}&date={d}")
            except Exception:
                continue              # 掃除済み・欠落ridはスキップ（1件で全体を止めない）
            # oddslog.php の action=get は素の配列を返す（dict包みではない）
            snaps = j if isinstance(j, list) else j.get("snapshots", [])
            if not isinstance(snaps, list):
                continue
            snaps = [s for s in snaps if s.get("mtp") is not None]
            if len(snaps) < 2:
                continue
            final = min(snaps, key=lambda s: s["mtp"])
            # 記録は5分間隔なので、締切直前ちょうどは取れないことが多い。
            # 「発走4分前以内の観測があれば最終とみなす」ぐらいに緩めないと0件になる。
            if final["mtp"] > 4:
                continue
            fav = None
            for num, e in (final.get("odds") or {}).items():
                if e.get("pop") == 1:
                    fav = num
                    break
            if not fav or not (final["odds"].get(fav) or {}).get("odds"):
                continue
            fo = final["odds"][fav]["odds"]
            n_used += 1
            for s in snaps:
                e = (s.get("odds") or {}).get(fav)
                if not e or not e.get("odds"):
                    continue
                for b in BANDS:
                    if b[0] <= s["mtp"] <= b[1]:
                        rows[b].append(100.0 * (fo - e["odds"]) / e["odds"])
                        break

    print(f"対象 {n_race:,}R 中、締切直前まで記録があったのは {n_used:,}R")
    if not n_used:
        print("まだ判定に足るデータが無い（オッズ記録が発走直前まで届いていない）")
        return 1
    print("\n残り分数ごとの「その時点のオッズ→締切直前」の変化率")
    print(f"{'帯':>10}{'件数':>7}{'中央値':>9}{'下振れ率':>9}{'5%点':>9}{'最悪':>9}")
    for b in BANDS:
        v = rows[b]
        if len(v) < 20:
            continue
        v.sort()
        down = 100.0 * sum(1 for x in v if x < 0) / len(v)
        p5 = v[max(0, int(len(v) * 0.05))]
        print(f"{f'{b[0]}-{b[1]}分前':>10}{len(v):>7,}{statistics.median(v):>8.1f}%"
              f"{down:>8.0f}%{p5:>8.1f}%{v[0]:>8.1f}%")
    print("\n読み方: マイナス=締切までにオッズが下がった（＝払戻が減る＝床が割れる方向）。")
    print("       5%点が床の安全マージンの目安。例: -8% なら複勝オッズを0.92倍で見て組む。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
