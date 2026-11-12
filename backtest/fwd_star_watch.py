# -*- coding: utf-8 -*-
"""最終レース・⭐単勝の「前向き検証」（金沢・川崎）

★なぜ前向き検証なのか★
  過去14年604Rでは通算ROI 107.9%、100%超が6/14年、直近3年連続100%超。
  ブートストラップの95%区間は [71.1%, 155.2%]（100%超の確率62.2%）。
  **偶然と切り捨てる証拠も、儲かると断定する証拠も無い。**
  604R・71的中では過去データをこれ以上見ても決着しない。
  だから今日から実際の予想を記録して、新しいデータで決着させる。

★⭐の定義★
  **予想人気**4〜8番 かつ 近走の最終コーナー通過位置が上位（≦0.35）。

  バックテストは bt_all.jsonl の `fpf`（近走平均先行度）を使った。
  こちらは保存済み予想の `cornerProf.c4` を使う。
  どちらも「最終コーナーの位置÷頭数」の近走加重平均だが、
  **参照する走数と重みが違う**（bt_all=直近5走 / 予想側=直近3走を1:0.7:0.5）。
  完全に同じ値にはならない。ここは既知のズレとして記録しておく。
  （これが課題#8「⭐定義の一致が先」の中身）

★オッズは使わない（事前予想に組み込むため）★
  当初は「実際の人気4〜8番」で定義したが、それだとオッズ発表を待つことになり
  **事前予想が出せなくなる**。予想を事前に出すのがこのサイトの根幹なので却下。

  代わりに **人気そのものを事前情報から予測する**。
  予想人気 = 近走平均着順の昇順（それだけ）。
  実測（60,000R）: 実際の1番人気を1位に置けたのが50.6%、3位以内78.4%、
  順位の誤差±2位以内が73.2%。⭐は「4〜8番人気」という帯なので、
  順位がピタリ当たる必要はなくこの精度で足りる。

  ★むしろ実人気版より成績が良い★（金沢・最終R・単勝）
    実人気版   604R ROI 107.9%（100%超の確率62.2%）
    予想人気版 530R ROI 125.6%（100%超の確率85.5%）
  予測の誤差で、市場がもっと評価していない馬を拾えるためと思われる。

入力: backtest/store/pred_data/*_46.json（金沢）
      backtest/nardata/race_*.zip（公式の着順・払戻）
出力: backtest/fwd_kanazawa_star.json
使い方: python backtest/fwd_kanazawa_star.py
"""
import csv
import glob
import io
import json
import os
import sys
import zipfile
from collections import defaultdict

# ★daily.py から子プロセスで呼ばれると標準出力が cp932 になり、"⭐" を print した
#   時点で UnicodeEncodeError で落ちていた（2026-08-05〜毎日 rc=1、json 保存まで
#   到達せず検証結果が n=4 で凍結）。出力をUTF-8に固定する。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRED = os.path.join(ROOT, "backtest", "store", "pred_data")
NARD = os.path.join(ROOT, "backtest", "nardata")
OUT = os.path.join(ROOT, "backtest", "fwd_star_watch.json")


POP_LO, POP_HI = 4, 8      # 予想人気のこの帯
C4_GATE = 0.35             # 近走の最終コーナー位置（小さいほど前）


def est_pop_key(x):
    """予想人気の並び替えキー＝近走平均着順（小さいほど上位人気と見る）。

    ★オッズを使わない★ pred_data の past5（直近5走の着順）から作る。
    当地/当距離の複勝率も足す版を試したが、単純な近走平均着順のほうが
    成績が良かった（ROI 125.6% vs 122.6%）ので、こちらを採る。
    """
    p5 = x.get("past5") or []
    rs = [p["rank"] for p in p5 if p and p.get("rank") is not None]
    return sum(rs) / len(rs) if rs else 99


def read_zip_csv(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix):
            return list(csv.reader(io.StringIO(
                z.read(n).decode("utf-8-sig", errors="replace"))))
    return []


def load_results():
    """(場名, 日付, R) -> {馬番: 着順} と 単勝払戻 {馬番: 円}"""
    ranks, tan = {}, {}
    for zp in sorted(glob.glob(os.path.join(NARD, "race_*.zip"))):
        try:
            z = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            continue
        for r in read_zip_csv(z, "_horselist.csv"):
            if len(r) < 32 or not r[1].isdigit() or not r[31].isdigit():
                continue
            ranks.setdefault((r[0], r[1], r[2]), {})[r[5]] = int(r[31])
        for r in read_zip_csv(z, "_payback.csv"):
            # 単勝は [4]組番 [5]払戻（docs/DATA_SOURCES.md）
            if len(r) < 6 or not r[1].isdigit():
                continue
            if r[4] and r[5].isdigit():
                tan.setdefault((r[0], r[1], r[2]), {})[r[4]] = int(r[5])
    return ranks, tan


# 監視対象。全場を予想人気で総ざらいした結果（bt_prepop_scan.py）から、
# 「100%超の確率70%以上 / 5年以上 / 100%超が35%以上の年 /
#   最良の1年を除いても90%以上」を満たしたものだけを載せる。
WATCH = [
    # ★本命★ 先行度を0.35→0.25に絞ると大きく伸びる。しきい値を動かすと
    #   0.45:105.8% 0.40:104.4% 0.35:126.3% 0.30:141.2% 0.25:190.6% 0.20:193.6%
    #   と**単調に上がる**ので、偶然の1マスではない。
    #   年別は8/14年が100%超、最良年(2025)を除いても162.7%。
    {"tc": "46", "name": "金沢", "min_stars": 1, "gate": 0.25,
     "past": "251R ROI190.6%（95%区間 97〜336 / 100%超確率97% / 8-14年）"},
    # 比較用。条件が緩いぶんレース数が倍あり、前向きの判定が早く進む。
    {"tc": "46", "name": "金沢", "min_stars": 1, "gate": 0.35,
     "past": "526R ROI126.3%（95%区間 84.7〜180.4 / 100%超確率86% / 6-14年）"},
    # ★川崎は先行度を絞っても伸びない（0.35:100.6% 0.30:89.9% 0.25:97.5%）。
    #   金沢のような勾配が無く、金沢固有の現象である可能性が高い。
    #   弱い候補として並走させ、差が出るか見る。
    {"tc": "45", "name": "川崎", "min_stars": 2, "gate": 0.35,
     "past": "267R ROI112.6%（95%区間 82.2〜146.7 / 100%超確率76% / 4-10年）"},
]


def run_one(w, ranks, tanpay):
    """1つの監視対象を集計する。判定できなかった理由も種類別に数える。"""
    files = sorted(glob.glob(os.path.join(PRED, "*_" + w["tc"] + ".json")))
    if not files:
        return None
    rows = []
    skip_few = skip_star = skip_result = 0
    for fp in files:
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if d.get("mode") != "nar":
            continue
        date = str(d.get("date"))
        races = [r for r in (d.get("races") or []) if r.get("no") is not None]
        if not races:
            continue
        last = max(races, key=lambda r: int(r["no"]))
        rk = [x for x in (last.get("ranked") or []) if x.get("num")]
        if len(rk) < 8:
            skip_few += 1
            continue

        # 予想人気（オッズ不要）＝近走平均着順の昇順
        order = sorted(rk, key=est_pop_key)
        est = {id(x): i + 1 for i, x in enumerate(order)}
        stars = [x for x in rk
                 if POP_LO <= est[id(x)] <= POP_HI
                 and (x.get("cornerProf") or {}).get("c4") is not None
                 and x["cornerProf"]["c4"] <= w["gate"]]
        if len(stars) < w["min_stars"]:
            skip_star += 1
            continue

        key = (w["name"], date, str(last["no"]))
        rmap = ranks.get(key)
        if not rmap:
            skip_result += 1
            continue
        tmap = tanpay.get(key, {})
        ret = sum(tmap.get(str(s["num"]), 0) for s in stars)
        rows.append({
            "date": date, "race": last["no"], "name": last.get("name"),
            "stars": [{"num": s["num"], "name": s.get("name"),
                       "est_pop": est[id(s)],
                       "c4": s["cornerProf"]["c4"],
                       "rank": rmap.get(str(s["num"])),
                       "tan": tmap.get(str(s["num"]), 0)} for s in stars],
            "inv": 100 * len(stars), "ret": ret, "hit": ret > 0,
        })

    rows.sort(key=lambda r: r["date"])
    inv = sum(r["inv"] for r in rows)
    ret = sum(r["ret"] for r in rows)
    return {
        "track": w["name"], "min_stars": w["min_stars"], "gate": w["gate"],
        "past": w["past"],
        "n": len(rows), "inv": inv, "ret": ret,
        "hits": sum(1 for r in rows if r["hit"]),
        "roi": (100 * ret / inv) if inv else None,
        "skipped": {"few_horses": skip_few, "no_star": skip_star,
                    "no_result": skip_result},
        "rows": rows,
    }


def main():
    ranks, tanpay = load_results()
    out = []
    print("最終レース・⭐単勝の前向き検証")
    print("  ⭐ = 予想人気" + str(POP_LO) + "〜" + str(POP_HI)
          + "番 かつ 近走の最終角位置が基準以下（基準は対象ごと）")
    print("  予想人気 = 近走平均着順の昇順（オッズは使わない＝事前に決まる）")
    print("")
    for w in WATCH:
        r = run_one(w, ranks, tanpay)
        if r is None:
            print(w["name"] + ": 保存済み予想が無い")
            print("")
            continue
        out.append(r)
        sk = r["skipped"]
        print("■ " + r["track"] + "（⭐" + str(r["min_stars"])
              + "頭以上 / 先行度<=" + str(r["gate"]) + "）")
        print("   過去の実測: " + r["past"])
        print("   判定できた " + str(r["n"]) + "R / 除外 頭数不足"
              + str(sk["few_horses"]) + " ⭐不足" + str(sk["no_star"])
              + " 結果待ち" + str(sk["no_result"]))
        if r["n"]:
            print("   投資{:,}円 払戻{:,}円 ROI {:.1f}% 的中{}/{}R".format(
                r["inv"], r["ret"], r["roi"], r["hits"], r["n"]))
            for x in r["rows"][-5:]:
                det = " ".join(
                    str(s["num"]) + "番(予想" + str(s["est_pop"]) + "人気→"
                    + str(s["rank"]) + "着"
                    + ((" {:,}円)".format(s["tan"])) if s["tan"] else ")")
                    for s in x["stars"])
                print("      " + x["date"] + " " + str(x["race"]) + "R " + det)
        print("")
    print("★判定には各場200R程度が要る（金沢・川崎とも年約50R＝4年ぶん）。")
    print("  それまで結論を出さない。")
    json.dump({"pop": [POP_LO, POP_HI], "c4_gate": C4_GATE, "watch": out},
              open(OUT, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    print("")
    print("出力: " + OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
