# -*- coding: utf-8 -*-
"""馬検索の索引を作る（馬名・父・母父・毛色・性別で絞り込める）

★全馬は載せない★
  13年で延べ7万頭以上いる。全部入れると索引が数MBになり、
  スマホで検索ページを開くたびに重い。**直近3年に出走した馬**に絞る
  （それより古い馬を調べる人は少なく、必要になったら期間を広げればいい）。

出力: deploy/db/horses_search.json
  [ [馬名, 父, 母父, 毛色, 性, 生年, 出走数, 勝利, 複勝率%, 複ROI%, 主戦場, 所属, 最終出走日, 馬主], ... ]
  ★馬主(14列目)は列20★ 会社名(（株）〜)も個人名も入る。最新の馬主で持つ。
  ★最終出走日(13列目)は「現役/引退」の絞り込みに使う★
    引退は公表されないので、最終出走からの経過で**推定するしかない**。
    日付を持たせておけば、判定の線をあとから変えられる（データを作り直さずに済む）。
  ★所属は「その馬を管理している調教師の所属」★（19列目）
  笠松の馬が大井に遠征しても所属は笠松のまま。「どこの馬か」で絞れる。
  ★配列の配列にする★ キー名を7万回繰り返すとサイズが倍になる。
"""
import csv
import glob
import io
import json
import os
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "backtest", "nardata")
OUT = os.path.join(ROOT, "deploy", "db", "horses_search.json")

ACTIVE_DAYS = 1100          # 直近3年


def read_zip_csv(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix):
            return list(csv.reader(io.StringIO(
                z.read(n).decode("utf-8-sig", errors="replace"))))
    return []


def main():
    # 馬名 -> [父, 母父, 毛色, 性, 生年, n, win, top3, ret, {場:回数}, 最終出走日]
    H = {}
    zips = sorted(glob.glob(os.path.join(WORK, "race_*.zip")))
    print(f"ZIP {len(zips)}本", flush=True)
    for i, zp in enumerate(zips):
        try:
            z = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            continue
        # 複勝払戻（回収率用）
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
            if len(r) < 32 or not r[1].isdigit() or not r[31].isdigit():
                continue
            name = r[6].strip()
            if not name:
                continue
            rk = int(r[31])
            e = H.get(name)
            if e is None:
                #        父            母父           毛色      性     生年
                e = H[name] = [r[11].strip(), r[13].strip(), r[9].strip(),
                               r[7].strip(), r[10][:4],
                               0, 0, 0, 0, defaultdict(int), "",
                               r[19].strip(),      # 調教師所属＝馬の所属
                               (r[20].strip() if len(r) > 20 else "")]  # 馬主
            e[5] += 1
            e[6] += (rk == 1)
            e[7] += (rk <= 3)
            e[8] += fuku.get((r[0], r[1], r[2]), {}).get(r[5], 0)
            e[9][r[0]] += 1
            if r[1] > e[10]:
                e[10] = r[1]
                e[11] = r[19].strip()      # 最新の所属で上書き（転厩に追随）
                if len(r) > 20:
                    e[12] = r[20].strip()  # 最新の馬主で上書き
        if (i + 1) % 40 == 0:
            print(f"  {i+1}/{len(zips)}  馬 {len(H):,}", flush=True)

    newest = max(e[10] for e in H.values())
    cutoff = (datetime.strptime(newest, "%Y%m%d")
              - timedelta(days=ACTIVE_DAYS)).strftime("%Y%m%d")
    out = []
    for name, e in H.items():
        if e[10] < cutoff:
            continue
        main_track = max(e[9], key=e[9].get) if e[9] else ""
        out.append([name, e[0], e[1], e[2], e[3], e[4],
                    e[5], e[6], round(100 * e[7] / e[5]),
                    round(100 * e[8] / (100 * e[5])), main_track, e[11], e[10], e[12]])
    out.sort(key=lambda x: -x[6])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    sz = os.path.getsize(OUT)
    print(f"出力: {os.path.relpath(OUT, ROOT)}  全馬{len(H):,} → 直近3年 {len(out):,}頭 / {sz/1024/1024:.1f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
