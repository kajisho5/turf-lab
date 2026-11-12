# -*- coding: utf-8 -*-
"""本番の「当地実績を反映」（既定ON）が C12 の効果を打ち消していないかを holdout で測る。

★なぜ要るか★
  tweet.html は C12 で並べ直した「後」に、当地補正と騎手当地補正を足して並べ直す（scoreRace）。
    当地補正   : s += 14 × (当地複勝率 − 0.33) × 2      （当地3走以上の馬だけ。LOCAL_MAG=14）
    騎手当地   : 上位6頭だけ s += 5 × clamp((騎手の当地複勝率% − 40)/8, −1, 1.5)（騎乗10回以上。JK_MAG=5）
  C12 の holdout 検証（単◎ROI +5.2 / 複◎ROI +2.7）はこの補正なしの◎で測った数字。
  しかも LTR は当地複勝率(wr)を特徴量として既に持っている＝補正は二重計上の可能性がある。

★再現の仕方★
  当地成績は公式CSVの当地成績文字列（r[27] "1-0-3-6"）＝本番が db.netkeiba から数える通算当地成績と同じ情報。
  騎手の当地成績は 2013年以降の公式データの累積（本番は keeeeeeba の通算。近似）。
  交流重賞の JRA 馬 +6 は再現しない（過去走の開催場が bt_all に無い。地方の平場には効かない）。

出力: 標準出力と backtest/store/discovery/c12_local.json
使い方: python backtest/bt_c12_local.py
"""
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np
import lightgbm as lgb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bt_train_ltr import fval, SPLIT                       # noqa: E402
from build_dataset import read_zip_csv, TC, num            # noqa: E402
from eval_bets import pay_single                           # noqa: E402

import re
import zipfile

WORK = os.path.join(HERE, "nardata")
C12_K = 2.0
LOCAL_MAG, JK_MAG = 14, 5          # tweet.html と同値


def counts(s):
    p = [int(x) for x in re.findall(r"\d+", s or "")]
    if len(p) < 4:
        return None
    return sum(p), p[0] + p[1] + p[2]


def build_side():
    """(rid, 馬番) -> (当地出走数, 当地複勝数, 騎手の当地騎乗数, 騎手の当地複勝率%)。騎手はリークなしの累積。"""
    jk = defaultdict(lambda: [0, 0])          # (場, 騎手) -> [騎乗, 複勝]
    side = {}
    for z in sorted(glob.glob(os.path.join(WORK, "race_*.zip"))):
        with zipfile.ZipFile(z) as zf:
            hl = read_zip_csv(zf, "_horselist.csv")    # build_dataset と同じ読み方
        if not hl:
            continue
        rows = defaultdict(list)
        for r in hl[1:]:
            if len(r) >= 36 and r[0] in TC:
                rows[(r[0], r[1], r[2])].append(r)
        for key in sorted(rows, key=lambda k: (k[1], k[0], int(k[2]))):
            ymd = key[1]
            rid = ymd[:4] + TC[key[0]] + ymd[4:] + key[2].zfill(2)
            done = []
            for r in rows[key]:
                j = (key[0], (r[14] or "").strip())
                if ymd >= SPLIT.replace("-", ""):
                    c = counts(r[27])
                    jn, jp = jk[j]
                    side[(rid, str(int(r[5])) if r[5].strip().isdigit() else r[5].strip())] = (
                        c[0] if c else 0, c[1] if c else 0, jn, (100.0 * jp / jn) if jn else None)
                rk = num(r[31], int)
                done.append((j, rk))
            for j, rk in done:                # レースが終わってから累積（リークなし）
                if rk is not None and j[1]:
                    jk[j][0] += 1
                    jk[j][1] += 1 if rk <= 3 else 0
    return side


def _z(a):
    sd = a.std()
    return (a - a.mean()) / sd if sd > 0 else a * 0


def apply_local(s, loc):
    """本番 scoreRace の当地補正→騎手当地補正を再現して、補正後の並べ替えスコアを返す"""
    sadj = s.copy()
    for i, (ln, lp, jn, jp) in enumerate(loc):
        lf = (lp / ln - 0.33) * 2 if ln >= 3 else 0.0
        sadj[i] += LOCAL_MAG * lf
    top6 = set(np.argsort(-sadj)[:6])
    for i, (ln, lp, jn, jp) in enumerate(loc):
        if i in top6 and jn >= 10 and jp is not None:
            jf = max(-1.0, min(1.5, (jp - 40) / 8))
            sadj[i] += JK_MAG * jf
    return sadj


def boot(d, n=4000, seed=0):
    d = np.asarray(d, float)
    rng = np.random.default_rng(seed)
    m = d[rng.integers(0, len(d), (n, len(d)))].mean(axis=1)
    return round(float(np.percentile(m, 2.5)), 1), round(float(np.percentile(m, 97.5)), 1)


def main():
    print("当地・騎手当地の再現データを作成中（公式ZIP 2013〜）...")
    side = build_side()
    print(f"  {len(side):,}頭ぶん")
    B = lgb.Booster(model_file=os.path.join(HERE, "ltr_model.txt"))
    BR = lgb.Booster(model_file=os.path.join(HERE, "ltr_res_model.txt"))
    F = B.feature_name()
    keys = ["old", "old_loc", "c12", "c12_loc"]
    R = {k: {"tan": [], "fuku": [], "pop": [], "hit3": []} for k in keys}
    nmiss = 0
    with open(os.path.join(WORK, "bt_all.jsonl"), encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            if rc["d"] < SPLIT or rc["tc"] == "65":
                continue
            pay = rc.get("pay") or {}
            if not pay.get("tan") or not pay.get("fuku"):
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            X = np.array([[fval(h, rc, k) for k in F] for h in hs], float)
            L = B.predict(X)
            comb = _z(L) + C12_K * _z(BR.predict(X))
            sc = comb.std()
            raw = L.mean() + L.std() * (comb / sc if sc > 0 else comb * 0)
            s_old, s_c12 = 50 + L * 12, 50 + raw * 12          # 本番の s と同じ尺度
            loc = []
            for h in hs:
                v = side.get((rc["rid"], str(int(h["n"]))))
                if v is None:
                    nmiss += 1
                    v = (0, 0, 0, None)
                loc.append(v)
            for k, s in (("old", s_old), ("old_loc", apply_local(s_old, loc)),
                         ("c12", s_c12), ("c12_loc", apply_local(s_c12, loc))):
                o = hs[int(np.argmax(s))]
                on = str(int(o["n"]))
                R[k]["tan"].append(pay_single(pay.get("tan"), on))
                R[k]["fuku"].append(pay_single(pay.get("fuku"), on))
                R[k]["pop"].append(o.get("pop") or np.nan)
                R[k]["hit3"].append(1 if o["rk"] <= 3 else 0)
    n = len(R["old"]["tan"])
    print(f"\nholdout {SPLIT}〜 地方(ばんえい除く) {n:,}R  当地データ欠け {nmiss:,}頭")
    out = {"n": n}
    for k, lab in (("old", "旧LTR"), ("old_loc", "旧LTR＋当地補正"), ("c12", "C12"), ("c12_loc", "C12＋当地補正（本番の既定）")):
        t, fk = np.mean(R[k]["tan"]), np.mean(R[k]["fuku"])
        h3, pp = 100 * np.mean(R[k]["hit3"]), np.nanmean(R[k]["pop"])
        out[k] = {"tan_roi": round(float(t), 1), "fuku_roi": round(float(fk), 1), "p3": round(float(h3), 1), "pop": round(float(pp), 2)}
        print(f"  {lab:<18} 単ROI {t:5.1f}  複ROI {fk:5.1f}  ◎複勝率 {h3:4.1f}%  ◎平均人気 {pp:.2f}")
    print()
    for a, b, lab in (("c12_loc", "c12", "当地補正がC12に与える影響（C12＋当地 − C12）"),
                      ("old_loc", "old", "当地補正が旧LTRに与える影響（旧＋当地 − 旧）"),
                      ("c12_loc", "old_loc", "本番で実際に起きる切替効果（C12＋当地 − 旧＋当地）"),
                      ("c12", "old", "検証済みのC12効果（補正なし・参考）")):
        dt = np.array(R[a]["tan"]) - np.array(R[b]["tan"])
        df = np.array(R[a]["fuku"]) - np.array(R[b]["fuku"])
        same = 100 * np.mean([x == y for x, y in zip(R[a]["pop"], R[b]["pop"])])
        out[f"{a}-{b}"] = {"tan": round(float(dt.mean()), 2), "tan_ci": boot(dt), "fuku": round(float(df.mean()), 2), "fuku_ci": boot(df)}
        print(f"  {lab}\n     単ROI {dt.mean():+.1f} {boot(dt)} / 複ROI {df.mean():+.1f} {boot(df)}")
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "c12_local.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
