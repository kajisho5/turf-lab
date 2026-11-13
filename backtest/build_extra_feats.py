# -*- coding: utf-8 -*-
"""追加の検証用の列（馬場差つきの時計・公式の成績欄・騎手との関係）を前走までの情報だけで作る

出力: backtest/nardata/extra_feats.jsonl  1行 = {"rid":..., "h": {馬番: {列: 値}}}
  A sv1/svb/sva … 馬場差つきの時計指数（近3走の 前走/最良/平均）
  B zn/z3/zout/dirr … 全成績の出走数・3着内率・手元の履歴に無い出走数・今日と同じ回りの3着内率
  C jdiff/jhn/jh3 … 騎手の格の上げ下げ・この騎手とこの馬の出走数と3着内率
詳しい定義は PREREG_extra_feats_20261113.md。未来の情報は使わない。
使い方: python3 backtest/build_extra_feats.py
"""
import glob, json, os, statistics, zipfile
from collections import defaultdict, deque
from build_time_feats import rd, t_run, TC, WORK

OUT = os.path.join(WORK, "extra_feats.jsonl")


def rec4(s):
    """'1-0-4-23' -> (出走数, 3着内数)"""
    try:
        a = [int(x) for x in (s or "").strip().split("-")]
        if len(a) != 4:
            return None
        return sum(a), a[0] + a[1] + a[2]
    except ValueError:
        return None


def main():
    zips = sorted(glob.glob(os.path.join(WORK, "race_*.zip")))
    win = defaultdict(lambda: deque(maxlen=300))    # (場,距離) -> 勝ち時計
    hsv = defaultdict(lambda: deque(maxlen=3))      # 馬名 -> 馬場差つきの時計指数
    cnt = defaultdict(int)                          # 馬名 -> 手元の履歴の出走数
    jk = defaultdict(lambda: [0, 0])                # 騎手 -> [騎乗, 3着内]
    lastj = {}                                      # 馬名 -> 前走の騎手

    def std(v, d):
        a = win[(v, d)]
        return statistics.median(a) if len(a) >= 20 else None

    def jrate(name):
        a = jk.get(name)
        return a[1] / a[0] if a and a[0] >= 50 else None

    n = 0
    with open(OUT + ".tmp", "w", encoding="utf-8") as fo:
        for zp in zips:
            with zipfile.ZipFile(zp) as z:
                rl, hl = rd(z, "_racelist.csv"), rd(z, "_horselist.csv")
            races = {(r[0], r[1], r[2]): (int(r[23]) if r[23].isdigit() else 0, r[22].strip())
                     for r in rl[1:] if len(r) >= 66 and r[0] in TC}
            rows = defaultdict(list)
            for r in hl[1:]:
                if len(r) >= 36 and r[0] in TC:
                    rows[(r[0], r[1], r[2])].append(r)
            days = defaultdict(list)                 # (日付, 場) -> レースのキー
            for key in sorted(rows, key=lambda k: (k[1], k[0], int(k[2]))):
                if key in races and races[key][0]:
                    days[(key[1], key[0])].append(key)
            for dk in sorted(days):
                pend = []                            # その日その場の (基準, 1ハロンあたり, 行)
                for key in days[dk]:
                    dist, turn = races[key]
                    out = {}
                    for r in rows[key]:
                        nm = r[6]
                        f = {}
                        sv = [x for x in list(hsv[nm])[::-1]] if nm in hsv else []
                        vals = [x for x in sv if x is not None]
                        if sv and sv[0] is not None:
                            f["sv1"] = sv[0]
                        if vals:
                            f["svb"] = max(vals); f["sva"] = round(sum(vals) / len(vals), 3)
                        a = rec4(r[24])
                        if a:
                            f["zn"] = a[0]
                            if a[0] >= 1:
                                f["z3"] = round(a[1] / a[0], 4)
                            f["zout"] = a[0] - cnt.get(nm, 0)
                        d4 = rec4(r[25] if turn == "左" else r[26] if turn == "右" else "")
                        if d4 and d4[0] >= 3:
                            f["dirr"] = round(d4[1] / d4[0], 4)
                        pj, cj = lastj.get(nm), r[14].strip()
                        if pj and cj:
                            a1, a0 = jrate(cj), jrate(pj)
                            if a1 is not None and a0 is not None:
                                f["jdiff"] = round(a1 - a0, 4)
                        j4 = rec4(r[17])
                        if j4:
                            f["jhn"] = j4[0]
                            if j4[0] >= 2:
                                f["jh3"] = round(j4[1] / j4[0], 4)
                        out[str(int(r[5])) if r[5].isdigit() else r[5]] = f
                    rid = key[1][:4] + TC[key[0]] + key[1][4:] + key[2].zfill(2)
                    fo.write(json.dumps({"rid": rid, "h": out}, ensure_ascii=False) + "\n")
                    n += 1
                    pend.append((key, std(key[0], dist), dist / 200.0))
                # ---- その日その場が終わってから、結果を履歴に足す ----
                dev = []
                for key, s0, per in pend:
                    w = [t_run(r[32]) for r in rows[key] if r[31].strip() == "1"]
                    if s0 and w and w[0]:
                        dev.append((w[0] - s0) / per)
                var = statistics.median(dev) if len(dev) >= 3 else None     # +なら時計のかかる馬場
                for key, s0, per in pend:
                    for r in rows[key]:
                        if not r[31].strip().isdigit():
                            continue
                        nm, t = r[6], t_run(r[32])
                        hsv[nm].append(round((s0 - t) / per + var, 3) if (s0 and t and var is not None) else None)
                        cnt[nm] += 1
                        if r[14].strip():
                            lastj[nm] = r[14].strip()
                            a = jk[r[14].strip()]; a[0] += 1; a[1] += int(r[31]) <= 3
                        if r[31].strip() == "1" and t:
                            win[(key[0], races[key][0])].append(t)
    os.replace(OUT + ".tmp", OUT)
    print(f"完了: {n:,}レース -> {OUT}")


if __name__ == "__main__":
    main()
