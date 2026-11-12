# -*- coding: utf-8 -*-
"""新馬戦（デビュー戦）専用データセットを作る

新馬戦は全馬に近走が無いので、通常モデルの特徴量（近走平均着順・実測先行力）が
一切使えない。代わりに使えるのは **血統・厩舎・騎手・馬体重・枠・性齢** だけ。
これらは bt_all.jsonl に入れていないので、専用に抽出する。

新馬判定: レース名に「新馬」を含む OR 出走馬の8割以上がその時点で初出走。
（月を日付順に処理し、その馬を過去に見たことがあるかで判定する）

出力: backtest/nardata/bt_debut.jsonl
{
  "rid","d","tc","r","fn","surf","dist","going","cls","name",
  "h":[{"n":馬番,"rk":着順,"pop":人気,"wk":枠,"sex":性,"age":齢,
        "sire":父,"dsire":母父,"jk":騎手,"tr":調教師,"wt":馬体重}...],
  "pay":{...}
}
"""
import csv, glob, io, json, os, re, sys, zipfile
from collections import defaultdict

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nardata")
OUT = os.path.join(WORK, "bt_debut.jsonl")

TC = {'門別': '30', '盛岡': '35', '水沢': '36', '浦和': '42', '船橋': '43', '大井': '44',
      '川崎': '45', '金沢': '46', '笠松': '47', '名古屋': '48', '園田': '50', '姫路': '51',
      '高知': '54', '佐賀': '55'}


def read_zip_csv(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix):
            return list(csv.reader(io.StringIO(z.read(n).decode("utf-8-sig", errors="replace"))))
    return []


def num(s, cast=int):
    try:
        return cast(s)
    except (TypeError, ValueError):
        return None


def pay_of(row):
    p = {}
    if row[4] and row[5].isdigit():
        p["tan"] = {row[4]: int(row[5])}
    fuku = {}
    for a, b in [(7, 8), (10, 11), (13, 14)]:
        if row[a] and row[b].isdigit():
            fuku[row[a]] = int(row[b])
    if fuku:
        p["fuku"] = fuku
    wide = {}
    for a, b, y in [(32, 33, 34), (36, 37, 38), (40, 41, 42)]:
        if row[a] and row[b] and row[y].isdigit():
            wide["-".join(sorted([row[a], row[b]], key=int))] = int(row[y])
    if wide:
        p["wide"] = wide
    if row[24] and row[26].isdigit():
        p["umaren"] = [sorted([row[24], row[25]], key=int), int(row[26])]
    if row[28] and row[30].isdigit():
        p["umatan"] = [[row[28], row[29]], int(row[30])]
    if row[44] and row[47].isdigit():
        p["sanpuku"] = [sorted([row[44], row[45], row[46]], key=int), int(row[47])]
    if row[49] and row[52].isdigit():
        p["santan"] = [[row[49], row[50], row[51]], int(row[52])]
    return p


def main():
    seen = set()          # これまでに出走を確認した馬名
    n_out = 0
    zips = sorted(glob.glob(os.path.join(WORK, "race_*.zip")))

    with open(OUT, "w", encoding="utf-8") as fo:
        for zp in zips:
            with zipfile.ZipFile(zp) as z:
                rl = read_zip_csv(z, "_racelist.csv")
                hl = read_zip_csv(z, "_horselist.csv")
                pb = read_zip_csv(z, "_payback.csv")

            races = {}
            for r in rl[1:]:
                if len(r) < 28 or r[0] not in TC:
                    continue
                fn = num(r[26])
                if not fn:
                    continue
                races[(r[0], r[1], r[2])] = {
                    "name": r[5], "surf": r[21], "dist": num(r[23]),
                    "going": r[25], "fn": fn, "cls": r[27],
                }
            pays = {}
            for r in pb[1:]:
                if len(r) >= 54 and r[0] in TC:
                    pays[(r[0], r[1], r[2])] = pay_of(r)

            rows = defaultdict(list)
            for r in hl[1:]:
                if len(r) >= 36 and r[0] in TC:
                    rows[(r[0], r[1], r[2])].append(r)

            for key in sorted(rows, key=lambda k: (k[1], k[0], int(k[2]))):
                rc = races.get(key)
                if not rc:
                    continue
                entries = rows[key]
                names = [r[6] for r in entries]
                fresh = sum(1 for nm in names if nm not in seen)
                debut = ("新馬" in (rc["name"] or "")) or (names and fresh / len(names) >= 0.8)

                if debut:
                    ymd = key[1]
                    rid = ymd[:4] + TC[key[0]] + ymd[4:] + key[2].zfill(2)
                    hs = []
                    for r in entries:
                        hs.append({
                            "n": r[5], "rk": num(r[31]), "pop": num(r[35]),
                            "wk": num(r[3]), "sex": r[7], "age": num(r[8]),
                            "sire": r[11].strip(), "dsire": r[13].strip(),
                            "jk": r[14].strip(), "tr": r[18].strip(),
                            "wt": num(r[22]),
                        })
                    fo.write(json.dumps({
                        "rid": rid, "d": ymd, "tc": TC[key[0]], "r": int(key[2]),
                        "fn": rc["fn"], "surf": rc["surf"], "dist": rc["dist"],
                        "going": rc["going"], "cls": rc["cls"], "name": rc["name"],
                        "h": hs, "pay": pays.get(key, {}),
                    }, ensure_ascii=False) + "\n")
                    n_out += 1

                seen.update(names)

            print(f"  {os.path.basename(zp)}: 新馬戦 累計 {n_out:,}R", flush=True)

    print(f"完了: {n_out:,}レース -> {OUT}")


if __name__ == "__main__":
    main()
