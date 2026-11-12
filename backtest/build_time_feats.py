# -*- coding: utf-8 -*-
"""時計の項目（走破タイム・上がり3F・最高タイム）を前走までの情報だけで作る（検証用の付け足しデータ）

出力: backtest/nardata/time_feats.jsonl  1行 = {"rid":..., "h": {馬番: {sf1,sfb,sfa,af1,afb,afa,btf}}}
  sf* = 時計指数。基準（その日より前の、同じ場×距離×馬場の勝ち時計の中央値・20件以上。足りなければ場×距離）
        − 自分の時計 を 200mあたりの秒にしたもの。大きいほど速い。
  af* = 上がり指数。そのレースの出走馬の上がり3F平均 − 自分の上がり3F。
  btf = 出馬表の「最高タイム」を今日の場×距離の基準と比べた指数。
未来の情報は使わない（特徴を作ってから、そのレースの結果を履歴に足す）。
使い方: python3 backtest/build_time_feats.py
"""
import csv, glob, io, json, os, statistics, zipfile
from collections import defaultdict, deque

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nardata")
OUT = os.path.join(WORK, "time_feats.jsonl")
TC = {'門別': '30', '盛岡': '35', '水沢': '36', '浦和': '42', '船橋': '43', '大井': '44',
      '川崎': '45', '金沢': '46', '笠松': '47', '名古屋': '48', '園田': '50', '姫路': '51',
      '高知': '54', '佐賀': '55'}


def rd(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix):
            return list(csv.reader(io.StringIO(z.read(n).decode("utf-8-sig", errors="replace"))))
    return []


def t_run(s):
    """'1311' -> 91.1秒"""
    s = (s or "").strip()
    if not s.isdigit() or len(s) < 3:
        return None
    v = int(s[:-3] or 0) * 60 + int(s[-3:-1]) + int(s[-1]) / 10.0
    return v if v > 20 else None


def t_best(s):
    """'1:28.5' -> 88.5秒"""
    s = (s or "").strip()
    try:
        if ":" in s:
            m, r = s.split(":")
            return int(m) * 60 + float(r)
        return float(s) if s else None
    except ValueError:
        return None


def fl(s):
    try:
        v = float(s)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def main():
    zips = sorted(glob.glob(os.path.join(WORK, "race_*.zip")))
    win = defaultdict(lambda: deque(maxlen=300))   # (場,距離,馬場) / (場,距離) -> 勝ち時計
    hist = defaultdict(lambda: deque(maxlen=3))    # 馬名 -> (sf, af)

    def std(v, d, g=None):
        if g is not None:
            a = win[(v, d, g)]
            if len(a) >= 20:
                return statistics.median(a)
        a = win[(v, d)]
        return statistics.median(a) if len(a) >= 20 else None

    n = 0
    with open(OUT + ".tmp", "w", encoding="utf-8") as fo:
        for zp in zips:
            with zipfile.ZipFile(zp) as z:
                rl, hl = rd(z, "_racelist.csv"), rd(z, "_horselist.csv")
            races = {(r[0], r[1], r[2]): (int(r[23]) if r[23].isdigit() else 0, r[25].strip()[:1])
                     for r in rl[1:] if len(r) >= 66 and r[0] in TC}
            rows = defaultdict(list)
            for r in hl[1:]:
                if len(r) >= 36 and r[0] in TC:
                    rows[(r[0], r[1], r[2])].append(r)
            for key in sorted(rows, key=lambda k: (k[1], k[0], int(k[2]))):
                if key not in races:
                    continue
                dist, going = races[key]
                if not dist:
                    continue
                per = dist / 200.0
                s_today = std(key[0], dist)            # 今日の馬場は発走前に確定しないので場×距離
                out = {}
                for r in rows[key]:
                    p = list(hist[r[6]])[::-1]
                    sfs = [x[0] for x in p if x[0] is not None]
                    afs = [x[1] for x in p if x[1] is not None]
                    bt = t_best(r[29])
                    f = {
                        "sf1": p[0][0] if p else None,
                        "sfb": max(sfs) if sfs else None,
                        "sfa": round(sum(sfs) / len(sfs), 3) if sfs else None,
                        "af1": p[0][1] if p else None,
                        "afb": max(afs) if afs else None,
                        "afa": round(sum(afs) / len(afs), 3) if afs else None,
                        "btf": round((s_today - bt) / per, 3) if (s_today and bt) else None,
                    }
                    out[str(int(r[5])) if r[5].isdigit() else r[5]] = {k: v for k, v in f.items() if v is not None}
                rid = key[1][:4] + TC[key[0]] + key[1][4:] + key[2].zfill(2)
                fo.write(json.dumps({"rid": rid, "h": out}, ensure_ascii=False) + "\n")
                n += 1
                # ---- ここから結果を履歴に足す ----
                s_run = std(key[0], dist, going)
                ag = [fl(r[34]) for r in rows[key]]
                ag = [a for a in ag if a]
                am = sum(ag) / len(ag) if len(ag) >= 3 else None
                for r in rows[key]:
                    if not r[31].strip().isdigit():
                        continue
                    t, a = t_run(r[32]), fl(r[34])
                    hist[r[6]].append((round((s_run - t) / per, 3) if (s_run and t) else None,
                                       round(am - a, 2) if (am and a) else None))
                    if r[31].strip() == "1" and t:
                        win[(key[0], dist, going)].append(t)
                        win[(key[0], dist)].append(t)
    os.replace(OUT + ".tmp", OUT)
    print(f"完了: {n:,}レース -> {OUT}")


if __name__ == "__main__":
    main()
