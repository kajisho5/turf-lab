# -*- coding: utf-8 -*-
"""騎手・調教師・血統を月ごとの補助データにする

★なぜ別ファイルにするのか★
  bt_all.jsonl（176,819レース）を作り直すと数十分かかるうえ、
  既存の検証結果と比較できなくなる。
  騎手・調教師・父・母父は horselist.csv に**最初から入っている**ので、
  レースIDで後から結合できる形で切り出す。

★月ごとに分ける理由★
  延べ178万頭ぶんを1つの辞書に載せるとメモリに乗らない。
  bt_all.jsonl は日付順に並んでいるので、月単位で読み込めば
  常に1か月ぶん（約1,100レース）だけをメモリに置けばよい。

出力: backtest/nardata/aux/YYYYMM.json
      { rid: { 馬番: [騎手, 調教師, 父, 母父] } }

使い方: python backtest/build_aux.py
"""
import csv
import glob
import io
import json
import os
import sys
import zipfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "backtest", "nardata")
OUT = os.path.join(WORK, "aux")

# build_dataset.py と同じ対応。ばんえいは平地と別物なので入れない
TC = {'門別': '30', '盛岡': '35', '水沢': '36', '浦和': '42', '船橋': '43', '大井': '44',
      '川崎': '45', '金沢': '46', '笠松': '47', '名古屋': '48', '園田': '50', '姫路': '51',
      '高知': '54', '佐賀': '55'}

# horselist.csv の列（docs/DATA_SOURCES.md 参照）
C_JYO, C_YMD, C_R, C_UMA = 0, 1, 2, 5
C_SIRE, C_DSIRE, C_JK, C_TR = 11, 13, 14, 18


def read_zip_csv(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix):
            return list(csv.reader(io.StringIO(
                z.read(n).decode("utf-8-sig", errors="replace"))))
    return []


def main():
    zips = sorted(glob.glob(os.path.join(WORK, "race_*.zip")))
    if not zips:
        sys.exit("race_*.zip が無い")
    os.makedirs(OUT, exist_ok=True)
    print(f"ZIP {len(zips)}本", flush=True)

    total = 0
    for i, zp in enumerate(zips):
        ym = os.path.basename(zp)[5:11]          # race_YYYYMM.zip
        dst = os.path.join(OUT, f"{ym}.json")
        if os.path.exists(dst):
            continue
        try:
            z = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            print(f"  !! 壊れている {os.path.basename(zp)}")
            continue

        m = defaultdict(dict)
        for r in read_zip_csv(z, "_horselist.csv"):
            if len(r) < 20 or not r[C_YMD].isdigit():
                continue
            tc = TC.get(r[C_JYO])
            if not tc:                            # ばんえい等
                continue
            ymd, rn = r[C_YMD], r[C_R]
            if not rn.isdigit():
                continue
            rid = f"{ymd[:4]}{tc}{ymd[4:8]}{int(rn):02d}"
            uma = r[C_UMA].strip()
            if not uma.isdigit():
                continue
            m[rid][str(int(uma))] = [
                r[C_JK].strip(), r[C_TR].strip(),
                r[C_SIRE].strip(), r[C_DSIRE].strip()]

        with open(dst, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, separators=(",", ":"))
        total += len(m)
        if (i + 1) % 24 == 0:
            print(f"  {i+1}/{len(zips)}  累計{total:,}レース", flush=True)

    files = sorted(glob.glob(os.path.join(OUT, "*.json")))
    size = sum(os.path.getsize(f) for f in files)
    print(f"\n出力: {len(files)}か月 / {size/1024/1024:.0f}MB  {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
