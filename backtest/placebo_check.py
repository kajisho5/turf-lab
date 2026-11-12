# -*- coding: utf-8 -*-
"""★プラシーボ対照★（配車係アーキテクチャ② / 問題再定義#193）

本番で公開した◎の成績を「同じレースでランダムに1頭選んだ場合の期待値」と比較する。
実力 = 実測 − プラシーボ。偶然と実力を分離する常設対照群。

なぜ要るか:
  「◎複勝率67%」は立派に見えるが、そのうち何ptが"どの馬を選んでも当たる分"なのかは
  比較対照が無いと言えない。ランダム対照はその底を与える（1番人気対照は市場との比較、
  ランダム対照は偶然との比較。両方あって初めて成績が読める）。

データ源: 本番サーバーの蓄積のみ（predictions.php=公開した予想 / results.php=確定結果）。
  バックテストではなく**実際に公開した予想**の成績であることが肝。
使い方: python backtest/placebo_check.py [日数(既定14)] [mode(nar/jra/both 既定both)]
"""
import io
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "https://seventh-well.com/odds"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 14
MODES = ["nar", "jra"] if (len(sys.argv) < 3 or sys.argv[2] == "both") else [sys.argv[2]]
JST = timezone(timedelta(hours=9))


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    today = datetime.now(JST)
    dates = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(1, DAYS + 1)]
    agg = {m: {"n": 0, "hit": 0, "ret": 0.0, "p_hit": 0.0, "p_ret": 0.0} for m in MODES}
    miss_res = 0
    for d in dates:
        for mode in MODES:
            try:
                pj = get(f"{BASE}/predictions.php?action=list&date={d}&mode={mode}")
            except Exception:
                continue
            races = []
            for rec in (pj.get("records") or []):
                for r in (rec.get("races") or []):
                    if r.get("skip") or not r.get("marks") or not r.get("race_id"):
                        continue
                    o = next((m2 for m2 in r["marks"] if m2.get("mk") == "◎"), None)
                    if o and o.get("num") is not None:
                        races.append((str(r["race_id"]), str(int(o["num"]))))
            if not races:
                continue
            ids = ",".join(rid for rid, _ in races)
            try:
                rj = get(f"{BASE}/results.php?action=get&ids={ids}")
            except Exception:
                continue
            results = rj.get("results") or {}
            for rid, onum in races:
                rec = results.get(rid)
                if not rec or not rec.get("ranks") or not (rec.get("pays") or {}).get("fukusho"):
                    miss_res += 1
                    continue
                ranks = rec["ranks"]
                fuku = rec["pays"]["fukusho"]
                field = len(ranks)
                if field < 5:
                    continue
                pay_of = {}
                for it in fuku:
                    try:
                        pay_of[str(int(it["nums"][0]))] = int(it["yen"])
                    except (KeyError, ValueError, TypeError, IndexError):
                        pass
                a = agg[mode]
                a["n"] += 1
                if onum in pay_of:
                    a["hit"] += 1
                    a["ret"] += pay_of[onum] / 100.0
                # プラシーボ: 同レースで一様ランダムに1頭選んだ期待値
                a["p_hit"] += len(pay_of) / field
                a["p_ret"] += sum(pay_of.values()) / field / 100.0
                # 市場ベースライン: 1番人気（finishersはv4.3.30以降の保存のみ・あれば集計）
                fin = rec.get("finishers") or []
                fav = next((f2 for f2 in fin if f2.get("pop") == 1), None)
                if fav and fav.get("num") is not None:
                    a.setdefault("m_n", 0)
                    a.setdefault("m_hit", 0)
                    a.setdefault("m_ret", 0.0)
                    a["m_n"] += 1
                    fn2 = str(int(fav["num"]))
                    if fn2 in pay_of:
                        a["m_hit"] += 1
                        a["m_ret"] += pay_of[fn2] / 100.0

    lines = ["", f"### プラシーボ対照（本番公開予想 直近{DAYS}日・{datetime.now(JST).strftime('%Y-%m-%d')}時点）"]
    lines.append("| mode | N | 実測◎複勝率 | プラシーボ複勝率 | 差(実力) | 実測◎複ROI | プラシーボROI | 差 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for m in MODES:
        a = agg[m]
        if not a["n"]:
            lines.append(f"| {m} | 0 | — | — | — | — | — | — |")
            continue
        hp = 100 * a["hit"] / a["n"]
        pp = 100 * a["p_hit"] / a["n"]
        rr = 100 * a["ret"] / a["n"]
        pr = 100 * a["p_ret"] / a["n"]
        lines.append(f"| {m} | {a['n']:,} | {hp:.1f}% | {pp:.1f}% | **{hp-pp:+.1f}pt** | {rr:.1f}% | {pr:.1f}% | {rr-pr:+.1f}pt |")
    # 市場(1番人気)ベースライン（finishers保存済みレースのみ）
    for m in MODES:
        a = agg[m]
        if a.get("m_n"):
            lines.append(f"| {m}:市場1人気 | {a['m_n']:,} | {100*a['m_hit']/a['m_n']:.1f}% | — | — | {100*a['m_ret']/a['m_n']:.1f}% | — | — |")
    lines.append(f"(結果未保存でスキップ: {miss_res}R)")
    lines.append("読み方: 差=偶然を超えた分。プラシーボROIは「どの馬を買っても返る分」＝控除後の床。")
    out = "\n".join(lines)
    print(out)
    with open(r"backtest/research_log.md", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(out + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
