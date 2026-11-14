# -*- coding: utf-8 -*-
"""ばんえいの予想の点数を毎朝作る（標準ライブラリだけ）

公式データ（月ごとのZIP。これから走るレースの出走表も入っている）から、ばんえい専用モデル（backtest/banei_model.json）で
1頭ずつ点数を出し、deploy/data/banei_pred.json に書く。tweet.html はこの点数で帯広の印を並べる。
- 書くのは「直近3日」と「これから走るレース」。材料と計算は学習の時と同じ（backtest/banei_feats.py）。
- ZIP は build_nar_index.py が先に取ってきたものを読む（ここでは取りに行かない）。
- 失敗しても公開は止めない（前の点数のまま。ページ側は点数が無いレースを今までの手作りの点数で並べる）。
使い方: python3 backtest/build_banei_pred.py --cache .nar_cache
"""
import argparse, datetime, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import banei_feats as BF


def main():
    ap = argparse.ArgumentParser(description="ばんえいの予想の点数を作る")
    ap.add_argument("--cache", default=os.path.join(HERE, "nardata_zip"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "deploy", "data", "banei_pred.json"))
    ap.add_argument("--today", default=None, help="YYYYMMDD（試験用。ふだんは日本時間の今日）")
    a = ap.parse_args()
    today = a.today or (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%Y%m%d")
    model = json.load(open(os.path.join(HERE, "banei_model.json"), encoding="utf-8"))
    if model["feat"] != BF.FE:
        raise SystemExit("モデルの材料の並びが banei_feats.py と違います（train_banei.py で作り直してください）")
    ds = BF.build(BF.load(a.cache))
    if not ds:
        raise SystemExit("ばんえいのレースが1つも読めませんでした（--cache の場所を確かめてください）")
    since = (datetime.date(int(today[:4]), int(today[4:6]), int(today[6:8])) - datetime.timedelta(days=3)).strftime("%Y%m%d")
    races = {}
    for o in ds:
        if o["d"] < since or o["n"] < 2:
            continue
        s = [BF.predict(model, x) for x in o["X"]]
        races["%s_%d" % (o["d"], o["r"])] = {"n": o["n"], "c": round(BF.conf(s), 4), "s": {k: round(v, 5) for k, v in zip(o["num"], s)}}
    last_done = max((o["d"] for o in ds if o["done"]), default=None)
    out = {"built": today, "asof": last_done, "model": model["name"], "c_battle": model["c_battle"], "c_aim": model["c_aim"],
           "from": since, "to": max((k.split("_")[0] for k in races), default=None), "races": races}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    days = sorted(set(k.split("_")[0] for k in races))
    print("ばんえいの点数: %d レース（%s）／結果が入っている最後の日 %s／モデル %s" % (len(races), "・".join(days), last_done, model["name"]))


if __name__ == "__main__":
    main()
