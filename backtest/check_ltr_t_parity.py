# -*- coding: utf-8 -*-
"""時計つきモデルの JS（core/ltr_model_t.js）と Python（LightGBM）が同じ値を出すか。
2026年のレースから約3,000頭を取り、両方で採点して最大の差を出す。差が 1e-6 を超えたら失敗。"""
import json, os, subprocess, sys
os.environ.update(LTR_NEWFEATS="pre", LTR_NODMS="1", LTR_TC="1", LTR_TIME="2")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.argv = ["x"]; sys.path.insert(0, HERE)
import numpy as np, lightgbm as lgb
import bt_train_ltr as T
L = lgb.Booster(model_file=os.path.join(HERE, "ltr_model_t.txt")); R = lgb.Booster(model_file=os.path.join(HERE, "ltr_res_model_t.txt"))
F = L.feature_name(); rows = []
with open(T.DATA, encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i % 40:
            continue
        rc = json.loads(line)
        if rc["d"] < "20260101":
            continue
        for h in rc["h"]:
            v = [T.fval(h, rc, k) for k in F]
            rows.append([None if x != x else x for x in v])
        if len(rows) >= 3000:
            break
X = np.array([[np.nan if x is None else x for x in r] for r in rows], float)
py = {"narT": L.predict(X).tolist(), "narTR": R.predict(X).tolist()}
js = subprocess.run(["node", "-e", """
const {ltrScoreT,LTR_MODEL_T}=require(process.argv[1]); const rows=JSON.parse(require('fs').readFileSync(0,'utf8'));
const F=LTR_MODEL_T.narT.feats; const out={narT:[],narTR:[]};
for(const r of rows){ const f={}; F.forEach((k,i)=>f[k]=r[i]); out.narT.push(ltrScoreT(f,'narT')); out.narTR.push(ltrScoreT(f,'narTR')); }
console.log(JSON.stringify(out));""", os.path.join(ROOT, "core", "ltr_model_t.js")], input=json.dumps(rows), capture_output=True, text=True, check=True)
js = json.loads(js.stdout); bad = 0
for k in py:
    d = max(abs(a - b) for a, b in zip(py[k], js[k]))
    print(f"{k}: {len(rows)}頭 最大の差 {d:.2e}")
    bad += d > 1e-6
sys.exit(1 if bad else 0)
