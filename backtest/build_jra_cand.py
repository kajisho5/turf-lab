# -*- coding: utf-8 -*-
"""中央: 「オッズに織り込まれていない材料」の候補を、前走までの情報だけで作る（検証用の別ファイル）。

出力: bt_jra.jsonl.cand  1行 = [rid, {馬番: {項目: 値}}]。bt_jra.jsonl 本体は変えない。
材料は今ある SE レコードだけ（新しく取り直さない）。位置は 2026-11-21 に実データで確かめた:
  斤量 288:291(×0.1kg) / ブリンカー 294:295 / 走破タイム 338:342(分1桁+秒2桁+0.1秒) /
  上がり3F 390:393(×0.1秒) / マイニング予想タイム 537:542 / マイニング予想順位 550:552

グループ
  time   : sf1 sfb sfa（時計指数：基準−自分 を200mあたり秒。直近1走/最良/平均・直近5走）
           af1 afb afa（上がり指数：そのレースの平均−自分）
           btf（今日と同じ場×距離×芝ダでの自己最速を、今日の基準と比べたもの）
  weight : kin（斤量）kchg（前走からの斤量の増減）blk（ブリンカー）blk1（初ブリンカー）
  body   : wt wd は bt_jra.jsonl にあるのでここでは作らない
  mining : dmr（JRA-VAN のマイニング予想順位）dmt（予想タイム：出走馬の平均−自分 を200mあたり秒）
           ※マイニングは「直前」に出る値。買う時点で見られるが、朝の予想には使えない。
未来の情報は使わない（項目を作ってから、そのレースの結果を履歴に足す）。
使い方: python backtest/build_jra_cand.py
"""
import bisect
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_jra_dataset import (DUMP, OUT, S_KEY, S_UMA, S_KETTO, S_FIN, R_KEY, R_DIST, R_TRACK,  # noqa: E402
                               R_SIBA_BABA, R_DIRT_BABA, num)

S_KIN, S_BLK, S_TIME, S_3F = slice(288, 291), slice(294, 295), slice(338, 342), slice(390, 393)
S_DMT, S_DMR = slice(537, 542), slice(550, 552)
N_PAST = 5
MIN_BASE = 20


def t_run(b):
    v = num(b)
    if not v:
        return None
    s = (v // 1000) * 60 + (v % 1000) / 10.0
    return s if s > 20 else None


def t_dm(b):
    v = num(b)                      # 分1桁+秒2桁+0.01秒2桁
    if not v:
        return None
    s = (v // 10000) * 60 + (v % 10000) / 100.0
    return s if s > 20 else None


def med(a):
    n = len(a)
    return a[n // 2] if n % 2 else (a[n // 2 - 1] + a[n // 2]) / 2


def main():
    ra = {}
    se = collections.defaultdict(list)
    for path in DUMP:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] == b"SE":
                    se[line[S_KEY]].append(line)
                elif line[:2] == b"RA":
                    ra[line[R_KEY]] = line
    for path in [x for x in os.environ.get("JRA_EXTRA_DUMPS", "").split(os.pathsep) if x]:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] == b"SE":
                    rows, kt = se[line[S_KEY]], line[S_KETTO]
                    for i, r in enumerate(rows):
                        if r[S_KETTO] == kt:
                            rows[i] = line
                            break
                    else:
                        rows.append(line)
                elif line[:2] == b"RA":
                    ra[line[R_KEY]] = line

    base_f = collections.defaultdict(list)     # (場,距離,芝ダ,馬場) -> 勝ち時計（並べ替え済み）
    base_c = collections.defaultdict(list)     # (場,距離,芝ダ)
    hist = collections.defaultdict(list)       # 馬 -> [(sf, af)]
    best = {}                                  # (馬,場,距離,芝ダ) -> 最速
    lastkin = {}
    blk_used = set()
    n = 0
    cov = collections.Counter()
    with open(OUT + ".cand", "w", encoding="utf-8") as fo:
        for k in sorted(se, key=lambda k: (k[:8].decode(), k[14:16].decode())):
            r_ra = ra.get(k)
            if not r_ra:
                continue
            dist = num(r_ra[R_DIST])
            tr = r_ra[R_TRACK].decode("ascii", "replace")[:1]
            if not dist or tr not in ("1", "2"):      # 障害は基準が作れないので外す
                continue
            jyo = k[8:10].decode()
            going = num(r_ra[R_SIBA_BABA] if tr == "1" else r_ra[R_DIRT_BABA])
            kf, kc = (jyo, dist, tr, going), (jyo, dist, tr)
            bl = base_f[kf] if len(base_f[kf]) >= MIN_BASE else base_c[kc]
            base = med(bl) if len(bl) >= MIN_BASE else None
            live = [r for r in se[k] if num(r[S_FIN])]
            if len(live) < 5:
                continue
            dms = [t_dm(r[S_DMT]) for r in live]
            dm_ok = [x for x in dms if x]
            dm_mean = sum(dm_ok) / len(dm_ok) if len(dm_ok) >= 0.8 * len(live) else None
            out = {}
            for r, dmt in zip(live, dms):
                h = r[S_KETTO]
                past = hist[h][-N_PAST:]
                sfs = [p[0] for p in past if p[0] is not None]
                afs = [p[1] for p in past if p[1] is not None]
                kin = (num(r[S_KIN]) or 0) / 10 or None
                blk = 1 if r[S_BLK] == b"1" else 0
                b = best.get((h,) + kc)
                dmr = num(r[S_DMR]) or None
                d = {
                    "sf1": past[-1][0] if past else None, "sfb": max(sfs) if sfs else None,
                    "sfa": sum(sfs) / len(sfs) if sfs else None,
                    "af1": past[-1][1] if past else None, "afb": max(afs) if afs else None,
                    "afa": sum(afs) / len(afs) if afs else None,
                    "btf": (base - b) / (dist / 200) if base and b else None,
                    "kin": kin, "kchg": kin - lastkin[h] if kin and h in lastkin else None,
                    "blk": blk, "blk1": 1 if blk and h not in blk_used else 0,
                    "dmr": dmr, "dmt": (dm_mean - dmt) / (dist / 200) if dm_mean and dmt else None,
                }
                out[str(num(r[S_UMA]))] = {a: (round(v, 3) if isinstance(v, float) else v) for a, v in d.items()}
                if k[:4] >= b"2015":
                    cov["n"] += 1
                    for a, v in d.items():
                        cov[a] += v is not None
            rid = k[:8].decode() + jyo + f"{int(k[14:16]):02d}"
            fo.write(json.dumps([rid, out]) + "\n")
            n += 1
            # ここから結果を履歴へ
            ts = [(r, t_run(r[S_TIME])) for r in live]
            f3 = [(num(r[S_3F]) or 0) / 10 for r in live]
            f3ok = [x for x in f3 if 25 < x < 60]
            f3m = sum(f3ok) / len(f3ok) if f3ok else None
            for (r, t), a in zip(ts, f3):
                h = r[S_KETTO]
                sf = (base - t) / (dist / 200) if base and t else None
                af = f3m - a if f3m and 25 < a < 60 else None
                hist[h].append((sf, af))
                if t and (best.get((h,) + kc) is None or t < best[(h,) + kc]):
                    best[(h,) + kc] = t
                kin = (num(r[S_KIN]) or 0) / 10
                if kin:
                    lastkin[h] = kin
                if r[S_BLK] == b"1":
                    blk_used.add(h)
                if num(r[S_FIN]) == 1 and t:
                    bisect.insort(base_f[kf], t)
                    bisect.insort(base_c[kc], t)
    print(f"出力 {os.path.basename(OUT)}.cand  {n:,}レース")
    if cov["n"]:
        print("2015年〜の値が入っている割合: " + "  ".join(
            f"{a} {100 * cov[a] / cov['n']:.0f}%" for a in ("sf1", "af1", "btf", "kin", "kchg", "blk", "blk1", "dmr", "dmt")))


if __name__ == "__main__":
    main()
