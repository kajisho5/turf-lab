# -*- coding: utf-8 -*-
"""馬・騎手の個別ページ用データを作る（SPAT4のような戦績表示のため）

★分割して置く★
  全馬の全レース履歴を1ファイルにすると数百MBになる。
  馬名の**ハッシュ先頭2桁**で256個に分け、必要な袋だけ読む。
  1袋あたり100〜200KB程度なので、1頭見るのに数百KBで済む。
  （馬ごとに1ファイルだと2.8万ファイルになり、FTPで配れない）

★騎手は数が少ないので1ファイル★
  400人程度なので分割は不要。

出力:
  deploy/db/h/{00〜ff}.json   馬 { 馬名: {p:プロフィール, r:[走った記録]} }
  deploy/db/j/index.json      騎手 { 騎手名: {summary, byTrack, byYear} }
  deploy/db/t/index.json      調教師（騎手と同形式。個別ページが無かったので追加）

★重賞(gr)は racelist.csv の競走種類名称(列4)から★
  普通/特別/重賞/準重賞の4値（実データで確認済み）。JRAのGI/GII/GIIIほど
  細かくないが、地方の重賞を判定できる唯一のクリーンな列。

1走の記録（配列で持つ。キー名を数百万回繰り返さないため）:
  [日付, 場, R, レース名, 頭数, 枠, 馬番, 人気, 着順, 騎手, 斤量, 馬体重, 増減, 複勝払戻]
"""
import csv
import glob
import hashlib
import io
import json
import os
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "backtest", "nardata")
OUT_H = os.path.join(ROOT, "deploy", "db", "h")
OUT_J = os.path.join(ROOT, "deploy", "db", "j")
OUT_T = os.path.join(ROOT, "deploy", "db", "t")

ACTIVE_DAYS = 1100          # 馬は直近3年に出走したものだけ（索引を軽くする）
KEEP_RUNS = 60              # 1頭あたり最大何走ぶん残すか（古い順に捨てる）

# horselist の列（docs/DATA_SOURCES.md）
C_JYO, C_YMD, C_R, C_WAKU, C_UMA, C_NAME = 0, 1, 2, 3, 5, 6
C_SEX, C_AGE, C_COLOR, C_BIRTH = 7, 8, 9, 10
C_SIRE, C_DAM, C_DSIRE, C_JK = 11, 12, 13, 14
C_KG, C_TR, C_WT, C_WD = 16, 18, 22, 23
C_RANK, C_POP = 31, 35


def read_zip_csv(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix):
            return list(csv.reader(io.StringIO(
                z.read(n).decode("utf-8-sig", errors="replace"))))
    return []


def bucket(name):
    return hashlib.md5(name.encode("utf-8")).hexdigest()[:2]


GRADED = {"重賞", "準重賞"}   # 「特別」は準重賞に満たない格。JRAのD格(重賞格付けなし)に近い


def main():
    horses = defaultdict(lambda: {"p": None, "r": []})

    def new_person():
        return {"n": 0, "w": 0, "t3": 0, "ret": 0,
                "tr": defaultdict(lambda: [0, 0, 0]),
                "yr": defaultdict(lambda: [0, 0, 0]),
                "gr": defaultdict(lambda: [0, 0])}
    jk = defaultdict(new_person)
    tr_agg = defaultdict(new_person)
    zips = sorted(glob.glob(os.path.join(WORK, "race_*.zip")))
    print(f"ZIP {len(zips)}本", flush=True)

    for i, zp in enumerate(zips):
        try:
            z = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            continue
        # レース名・距離・競走種類(普通/特別/重賞/準重賞)
        rl = {}
        for r in read_zip_csv(z, "_racelist.csv"):
            if len(r) > 26 and r[1].isdigit():
                rl[(r[0], r[1], r[2])] = (r[5].strip(), r[23].strip(), r[26].strip(), r[4].strip())
        # 複勝払戻
        fuku = {}
        for r in read_zip_csv(z, "_payback.csv"):
            if len(r) < 10 or not r[1].isdigit():
                continue
            d = fuku.setdefault((r[0], r[1], r[2]), {})
            # ★複勝の列位置★ payback.csv の並びは
            #   [4]単勝馬番 [5]単勝払戻 [6]人気
            #   [7]複勝馬番 [8]複勝払戻 [9]人気
            #   [10][11][12] 2頭目 / [13][14][15] 3頭目 / [16]〜ワイド
            # ★以前ここを (4,5)(6,7)(8,9) と書いていた（重大な誤り）★
            #   ・単勝の払戻を複勝として集計していた（回収率が過大になる）
            #   ・(6,7) は「人気→馬番」を拾うので、着外の馬に数円の払戻が付いた
            #   ・本物の複勝払戻を一度も使っていなかった
            #   実際に馬の戦績ページで6着に「9円」が出て気づいた。
            #   分母の取り方だけでなく、**分子の列位置**も回収率を壊す。
            for a, b in ((7, 8), (10, 11), (13, 14)):
                if r[a] and r[b].isdigit():
                    d[r[a]] = int(r[b])

        for r in read_zip_csv(z, "_horselist.csv"):
            if len(r) < 36 or not r[C_YMD].isdigit() or not r[C_RANK].isdigit():
                continue
            name = r[C_NAME].strip()
            if not name:
                continue
            key = (r[C_JYO], r[C_YMD], r[C_R])
            rname, dist, tosu, rkind = rl.get(key, ("", "", "", ""))
            rank = int(r[C_RANK])
            pay = fuku.get(key, {}).get(r[C_UMA], 0)
            jkname = r[C_JK].strip()
            trname = r[C_TR].strip()

            h = horses[name]
            if h["p"] is None:
                h["p"] = [r[C_SEX], r[C_COLOR], r[C_BIRTH][:4],
                          r[C_SIRE].strip(), r[C_DAM].strip(), r[C_DSIRE].strip(),
                          trname]
            h["r"].append([r[C_YMD], r[C_JYO], r[C_R], rname, tosu,
                           r[C_WAKU], r[C_UMA], r[C_POP], rank, jkname,
                           r[C_KG], r[C_WT], r[C_WD], pay, dist])

            for name2, store in ((jkname, jk), (trname, tr_agg)):
                if not name2:
                    continue
                e = store[name2]
                e["n"] += 1
                e["w"] += (rank == 1)
                e["t3"] += (rank <= 3)
                e["ret"] += pay
                t = e["tr"][r[C_JYO]]
                t[0] += 1; t[1] += (rank == 1); t[2] += (rank <= 3)
                y = e["yr"][r[C_YMD][:4]]
                y[0] += 1; y[1] += (rank == 1); y[2] += (rank <= 3)
                if rkind in GRADED:
                    g = e["gr"][rkind]
                    g[0] += 1; g[1] += (rank == 1)
        if (i + 1) % 40 == 0:
            print(f"  {i+1}/{len(zips)}  馬{len(horses):,} 騎手{len(jk):,} 調教師{len(tr_agg):,}", flush=True)

    # --- 馬: 直近3年に出走したものだけ、袋に分けて書く ---
    newest = max(max(x[0] for x in h["r"]) for h in horses.values() if h["r"])
    cutoff = (datetime.strptime(newest, "%Y%m%d")
              - timedelta(days=ACTIVE_DAYS)).strftime("%Y%m%d")
    buckets = defaultdict(dict)
    kept = 0
    for name, h in horses.items():
        if not h["r"]:
            continue
        h["r"].sort(key=lambda x: x[0], reverse=True)     # 新しい順
        if h["r"][0][0] < cutoff:
            continue
        buckets[bucket(name)][name] = {"p": h["p"], "r": h["r"][:KEEP_RUNS]}
        kept += 1
    os.makedirs(OUT_H, exist_ok=True)
    total = 0
    for b, d in buckets.items():
        p = os.path.join(OUT_H, f"{b}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        total += os.path.getsize(p)
    print(f"\n馬: {kept:,}頭 / {len(buckets)}袋 / 合計{total/1024/1024:.0f}MB "
          f"（1袋平均 {total/max(len(buckets),1)/1024:.0f}KB）")

    def dump_person(store, out_dir, label, min_n=50):
        out = {}
        for name, e in store.items():
            if e["n"] < min_n:
                continue
            out[name] = {
                "n": e["n"], "w": e["w"], "t3": e["t3"],
                "roi": round(100 * e["ret"] / (100 * e["n"]), 1),
                "tr": {k: v for k, v in sorted(e["tr"].items(), key=lambda x: -x[1][0])[:20]},
                "yr": {k: v for k, v in sorted(e["yr"].items())},
                "gr": {k: v for k, v in sorted(e["gr"].items(), key=lambda x: -x[1][1])},
            }
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, "index.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{label}: {len(out):,}人 / {os.path.getsize(p)/1024:.0f}KB")
        return out

    dump_person(jk, OUT_J, "騎手")
    dump_person(tr_agg, OUT_T, "調教師")
    return 0


if __name__ == "__main__":
    sys.exit(main())
