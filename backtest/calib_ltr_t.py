# -*- coding: utf-8 -*-
"""時計つきモデル（mv 2.3）の ◎3着内見込みの表を作って deploy/data/ltr_calib.json の narT に入れる。
calib_ltr.py の narC12 と同じ作り方（2023年以降・10分位）。ほかのキーは触らない。
ついでに、点数の幅が今のモデルと比べてどれだけ変わるかも出す（判定の閾値への影響を見るため）。
使い方: python3 backtest/calib_ltr_t.py
"""
import json, os, sys
os.environ.update(LTR_NEWFEATS="pre", LTR_NODMS="1", LTR_TC="1", LTR_TIME="1")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.argv = ["x"]; sys.path.insert(0, HERE)
import numpy as np, lightgbm as lgb
import bt_train_ltr as T
K = 2.0
L33 = lgb.Booster(model_file=os.path.join(HERE, "ltr_model.txt")); R33 = lgb.Booster(model_file=os.path.join(HERE, "ltr_res_model.txt"))
L40 = lgb.Booster(model_file=os.path.join(HERE, "ltr_model_t40.txt")); R40 = lgb.Booster(model_file=os.path.join(HERE, "ltr_res_model_t40.txt"))
F33, F40 = L33.feature_name(), L40.feature_name()
assert R33.feature_name() == F33 and R40.feature_name() == F40


def z(a):
    sd = a.std()
    return (a - a.mean()) / sd if sd > 0 else a * 0


def rawp(L, R, X):
    s = L.predict(X); comb = z(s) + K * z(R.predict(X)); sc = comb.std()
    return s.mean() + s.std() * (comb / sc if sc > 0 else comb * 0)


cs, hits, g_old, g_new, sd_old, sd_new = [], [], [], [], [], []
with open(T.DATA, encoding="utf-8") as f:
    for line in f:
        rc = json.loads(line)
        if rc["d"] < "20230101":
            continue
        hs = [h for h in rc["h"] if h.get("rk") is not None]
        if len(hs) < 5:
            continue
        X40 = np.array([[T.fval(h, rc, k) for k in F40] for h in hs], float)
        X33 = np.array([[T.fval(h, rc, k) for k in F33] for h in hs], float)
        o, s = rawp(L33, R33, X33), rawp(L40, R40, X40)
        top = int(np.argmax(s)); spread = float(s.max() - s.min()) or 1.0
        s2 = float(np.partition(s, -2)[-2])
        cs.append(0.6 * (float(s[top]) - float(s.mean())) / spread + 0.4 * (float(s[top]) - s2) / spread)
        hits.append(int(hs[top]["rk"]) <= 3)
        so, sn = np.sort(o)[::-1], np.sort(s)[::-1]
        g_old.append((so[0] - so[1]) * 12); g_new.append((sn[0] - sn[1]) * 12); sd_old.append(o.std()); sd_new.append(s.std())
cs, hits = np.array(cs), np.array(hits)
edges = np.quantile(cs, np.arange(1, 10) / 10.0); bins = np.searchsorted(edges, cs)
p = [round(100.0 * hits[bins == b].mean(), 1) for b in range(10)]; n = [int((bins == b).sum()) for b in range(10)]
print(f"[narT] {len(cs):,}R 分位→3着内%: {p}")
go, gn = np.array(g_old), np.array(g_new)
print(f"点数の幅（レース内の標準偏差の平均）: 今 {np.mean(sd_old):.4f} → 新 {np.mean(sd_new):.4f}（{np.mean(sd_new)/np.mean(sd_old):.3f}倍）")
for th in (4, 8):
    print(f"◎−○の点差が{th}以上のレース: 今 {100*(go>=th).mean():.1f}% → 新 {100*(gn>=th).mean():.1f}%")
out = os.path.join(ROOT, "deploy", "data", "ltr_calib.json")
j = json.load(open(out, encoding="utf-8"))
j["narT"] = {"edges": [round(float(e), 4) for e in edges], "p": p, "n": n}
if "narT=" not in j.get("note", ""):
    j["note"] = j.get("note", "") + "。narT=時計つきモデル(mv2.3)の並びで作った地方用"
json.dump(j, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("書き出し:", os.path.relpath(out, ROOT))
