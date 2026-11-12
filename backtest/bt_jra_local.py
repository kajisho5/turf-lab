# -*- coding: utf-8 -*-
"""中央: 本番の「当地実績を反映」（既定ON・中央モードでも効く）が中央LTRの◎を良くしているかを holdout で測る。

地方版 bt_c12_local.py と同じ再現。中央はC12未導入なので「中央LTR」vs「中央LTR＋当地補正」だけ。
  当地補正   : s += 14 × (当地複勝率 − 0.33) × 2      （当地3走以上。bt_jra の wr がちょうどこの定義）
  騎手当地   : 上位6頭だけ s += 5 × clamp((騎手の当地複勝率% − 40)/8, −1, 1.5)（騎乗10回以上）
  騎手の当地成績は JV-Data ダンプ（1985〜）から累積（リークなし）。本番は keeeeeeba の通算＝近似。
出力: 標準出力と backtest/store/discovery/jra_local.json
使い方: python backtest/bt_jra_local.py
"""
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
from bt_train_ltr import fval, SPLIT                                   # noqa: E402
from build_jra_dataset import DUMP, S_KEY, S_UMA, S_FIN, S_JK, num     # noqa: E402
from eval_bets import pay_single                                       # noqa: E402
from bt_c12_local import apply_local, boot                             # noqa: E402  本番と同じ補正式


def jockey_side():
    """(rid, 馬番) -> (None, None, 騎手の当地騎乗数, 騎手の当地複勝率%)"""
    se = defaultdict(list)
    for path in DUMP:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                if line[:2] == b"SE":
                    k = line[S_KEY]
                    se[k].append((num(line[S_UMA]), line[S_JK].decode("cp932", "replace").strip(), num(line[S_FIN])))
    keys = sorted(se, key=lambda k: (k[:8].decode(), k[14:16].decode()))
    jk = defaultdict(lambda: [0, 0])
    side = {}
    for k in keys:
        date, jyo, rno = k[:8].decode(), k[8:10].decode(), int(k[14:16])
        rid = date + jyo + f"{rno:02d}"
        rows = se[k]
        if date >= SPLIT:
            for uma, nm, fin in rows:
                n_, p_ = jk[(jyo, nm)]
                side[(rid, str(uma))] = (n_, (100.0 * p_ / n_) if n_ else None)
        for uma, nm, fin in rows:                 # 走り終えてから累積
            if fin and nm:
                jk[(jyo, nm)][0] += 1
                jk[(jyo, nm)][1] += 1 if fin <= 3 else 0
    return side


def main():
    print("騎手の当地成績を JV-Data から再構築中...")
    side = jockey_side()
    print(f"  {len(side):,}頭ぶん")
    B = lgb.Booster(model_file=os.path.join(HERE, "ltr_model_jra.txt"))
    F = B.feature_name()
    R = {k: {"tan": [], "fuku": [], "pop": [], "hit3": []} for k in ("ltr", "ltr_loc", "ltr_hloc")}
    nmiss = 0
    with open(os.path.join(HERE, "nardata", "bt_jra.jsonl"), encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            if rc["d"] < SPLIT:
                continue
            pay = rc.get("pay") or {}
            if not pay.get("tan") or not pay.get("fuku"):
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            X = np.array([[fval(h, rc, k) for k in F] for h in hs], float)
            s = 50 + B.predict(X) * 12
            loc = []
            for h in hs:
                wr = h.get("wr")                      # 当地3走以上の複勝率（bt_jra の定義＝本番の n>=3 と同じ）
                j = side.get((rc["rid"], str(int(h["n"]))))
                if j is None:
                    nmiss += 1
                    j = (0, None)
                # apply_local の入力形 (当地出走, 当地複勝, 騎手騎乗, 騎手複勝率%) に合わせる
                loc.append((3, 3 * wr, j[0], j[1]) if wr is not None else (0, 0, j[0], j[1]))
            loc_h = [(a, b, 0, None) for a, b, _, _ in loc]   # 馬の当地補正だけ（騎手当地なし）
            for k, sc in (("ltr", s), ("ltr_loc", apply_local(s, loc)), ("ltr_hloc", apply_local(s, loc_h))):
                o = hs[int(np.argmax(sc))]
                on = str(int(o["n"]))
                R[k]["tan"].append(pay_single(pay.get("tan"), on))
                R[k]["fuku"].append(pay_single(pay.get("fuku"), on))
                R[k]["pop"].append(o.get("pop") or np.nan)
                R[k]["hit3"].append(1 if o["rk"] <= 3 else 0)
    n = len(R["ltr"]["tan"])
    print(f"\nholdout {SPLIT}〜 中央 {n:,}R  騎手データ欠け {nmiss:,}頭")
    out = {"n": n}
    for k, lab in (("ltr", "中央LTR"), ("ltr_hloc", "中央LTR＋馬の当地補正だけ"), ("ltr_loc", "中央LTR＋当地補正（本番の既定）")):
        t, fk = np.mean(R[k]["tan"]), np.mean(R[k]["fuku"])
        h3, pp = 100 * np.mean(R[k]["hit3"]), np.nanmean(R[k]["pop"])
        out[k] = {"tan_roi": round(float(t), 1), "fuku_roi": round(float(fk), 1), "p3": round(float(h3), 1), "pop": round(float(pp), 2)}
        print(f"  {lab:<22} 単ROI {t:5.1f}  複ROI {fk:5.1f}  ◎複勝率 {h3:4.1f}%  ◎平均人気 {pp:.2f}")
    for a, lab in (("ltr_loc", "当地補正（馬＋騎手・本番）の影響"), ("ltr_hloc", "馬の当地補正だけの影響")):
        dt = np.array(R[a]["tan"]) - np.array(R["ltr"]["tan"])
        df = np.array(R[a]["fuku"]) - np.array(R["ltr"]["fuku"])
        dh = 100 * (np.array(R[a]["hit3"]) - np.array(R["ltr"]["hit3"]))
        out[a + "-ltr"] = {"tan": round(float(dt.mean()), 2), "tan_ci": boot(dt), "fuku": round(float(df.mean()), 2),
                           "fuku_ci": boot(df), "p3": round(float(dh.mean()), 2), "p3_ci": boot(dh)}
        print(f"  {lab}\n     単ROI {dt.mean():+.1f} {boot(dt)} / 複ROI {df.mean():+.1f} {boot(df)} / ◎複勝率 {dh.mean():+.1f}pt {boot(dh)}")
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "jra_local.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
