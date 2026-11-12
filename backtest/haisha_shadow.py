# -*- coding: utf-8 -*-
"""★配車係シャドー★（配車係アーキテクチャ③ / 問題再定義#91+#55）

「予想する」の前に「このレースは読めるか」を判定する配車係を、
まず**影(ログのみ)**で運用する。本番表示・蓄積記録は一切変えない。
実測が溜まって分類の複勝率が安定したら表示への昇格を検討する（#298 影の運用）。

分類（事前に分かる情報だけ・保存済み予想から）:
  読める   : oProb>=72（較正表の上位帯。実測74-82%complexity帯）
  半読み   : oProb 60-71
  読めない : oProb<60 ／ oProbなし（LTR不発=データ薄）／ firmO<40（混戦）
  理由も分類: データ不足 / 混戦 / 通常弱

出力: backtest/shadow_haisha.jsonl に1レース1行（rid重複は追記しない）
      ＋ 累積の分類別実測複勝率を表示
使い方: python backtest/haisha_shadow.py [日数(既定3)]   ※daily.pyから毎朝2日分
"""
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "https://seventh-well.com/odds"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGF = os.path.join(ROOT, "backtest", "shadow_haisha.jsonl")
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
JST = timezone(timedelta(hours=9))


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def classify(r):
    """保存済み予想レコード1件 → (label, reason)
    ★oProbは「◎がLTRトップの時だけ」保存される仕様★（無い＝データ不足ではない）。
    無い場合は firmO にフォールバックする。firmOも無ければデータ不足。"""
    op = r.get("oProb")
    fo = r.get("firmO")
    if fo is not None and fo < 40:
        return "読めない", "混戦(firmO<40)"
    if op is not None:
        if op >= 72:
            return "読める", "oProb高"
        if op >= 60:
            return "半読み", "oProb中"
        return "読めない", "oProb低"
    if fo is not None:
        if fo >= 60:
            return "読める", "firmO高(oProb無)"
        return "半読み", "firmO中(oProb無)"
    return "読めない", "データ不足"


def main():
    seen = set()
    if os.path.exists(LOGF):
        with open(LOGF, encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen.add(json.loads(line)["rid"])
                except (json.JSONDecodeError, KeyError):
                    pass
    today = datetime.now(JST)
    dates = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(1, DAYS + 1)]
    added = 0
    with open(LOGF, "a", encoding="utf-8", newline="\n") as out:
        for d in dates:
            for mode in ("nar", "jra"):
                try:
                    pj = get(f"{BASE}/predictions.php?action=list&date={d}&mode={mode}")
                except Exception:
                    continue
                cand = []
                for rec in (pj.get("records") or []):
                    for r in (rec.get("races") or []):
                        if r.get("skip") or not r.get("marks") or not r.get("race_id"):
                            continue
                        if str(r["race_id"]) in seen:
                            continue
                        o = next((m for m in r["marks"] if m.get("mk") == "◎"), None)
                        if o:
                            cand.append((r, str(int(o["num"]))))
                if not cand:
                    continue
                ids = ",".join(str(r["race_id"]) for r, _ in cand)
                try:
                    rj = get(f"{BASE}/results.php?action=get&ids={ids}")
                except Exception:
                    continue
                results = rj.get("results") or {}
                for r, onum in cand:
                    rid = str(r["race_id"])
                    res = results.get(rid)
                    if not res or not res.get("ranks"):
                        continue                     # 結果が出てから拾う（次回の実行で）
                    rk = res["ranks"].get(onum)
                    label, reason = classify(r)
                    # ★事前シグナルは今のうちからスキーマに入れる★（後で境界を引き直す材料。
                    #   gap=◎と2位のスコア差はrankedから復元できる）
                    gap = None
                    try:
                        rr = r.get("ranked") or []
                        if len(rr) >= 2 and rr[0].get("s") is not None and rr[1].get("s") is not None:
                            gap = round(float(rr[0]["s"]) - float(rr[1]["s"]), 2)
                    except (TypeError, ValueError):
                        pass
                    row = {"date": d, "mode": mode, "rid": rid, "tc": rid[4:6],
                           "label": label, "reason": reason,
                           "oProb": r.get("oProb"), "firmO": r.get("firmO"), "gap": gap,
                           "field": len(res["ranks"]), "o_rank": rk,
                           "hit": (rk is not None and rk <= 3)}
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    seen.add(rid)
                    added += 1

    # 累積サマリ＋昇格判定（#298 影→本番の昇格を機械で決める）
    rows = []
    with open(LOGF, encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    def wilson(k, n, z=1.96):
        """複勝率のWilson 95%区間（小標本で過信しないため）"""
        if not n:
            return (0.0, 0.0, 1.0)
        p = k / n
        den = 1 + z * z / n
        c = (p + z * z / (2 * n)) / den
        h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
        return (p, max(0.0, c - h), min(1.0, c + h))

    print(f"配車係シャドー: 今回追加 {added}R / 累積 {len(rows)}R")
    stats = {}
    print(f"{'分類':<6}{'N':>5}{'◎複勝率':>9}  95%区間")
    for lab in ("読める", "半読み", "読めない"):
        g = [x for x in rows if x["label"] == lab]
        if g:
            p, lo, hi = wilson(sum(1 for x in g if x["hit"]), len(g))
            stats[lab] = (len(g), p, lo, hi)
            print(f"{lab:<6}{len(g):>5}{100*p:>8.1f}%  [{100*lo:.1f}, {100*hi:.1f}]")
    g = [x for x in rows if x["label"] == "読めない"]
    if g:
        print("  読めない内訳:")
        for rs in sorted({x["reason"] for x in g}):
            gg = [x for x in g if x["reason"] == rs]
            print(f"    {rs:<18} N={len(gg):<4} ◎複勝率 {100*sum(1 for x in gg if x['hit'])/len(gg):.1f}%")
    # ★昇格判定★ 各分類N>=150（計450+）かつ「読める」の下限 > 「読めない」の上限（区間が離れる）
    MIN_N = 150
    if all(lab in stats and stats[lab][0] >= MIN_N for lab in ("読める", "半読み", "読めない")):
        ok = stats["読める"][2] > stats["読めない"][3]
        print("\n★昇格判定★ " + ("合格: 分類は統計的に分離。表示(堅い/荒れ注意ラベル)への昇格を提案してよい"
                              if ok else
                              "不合格: 95%区間が重なる＝分類は未実証。境界を引き直すか蓄積を続ける"))
    else:
        need = {lab: MIN_N - stats.get(lab, (0,))[0] for lab in ("読める", "半読み", "読めない")}
        print(f"\n昇格判定はデータ不足（各分類{MIN_N}R必要・不足: " +
              " ".join(f"{k}あと{max(0,v)}" for k, v in need.items()) + "）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
