# -*- coding: utf-8 -*-
"""Cloudflare(D1) の予想をローカルの backtest/store/pred_data/ へ同期する
（sync_pred_data.py の WinSCP 版の置き換え。deploy_cf.json の use_cloudflare が true の時に使われる）

★取得のみ・削除しない★ 中身が同じファイルは書かない。
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOCAL = os.path.join(ROOT, "backtest", "store", "pred_data")
sys.path.insert(0, HERE)
from migrate import token, UA  # noqa: E402


def main():
    conf = json.load(open(os.path.join(HERE, "deploy_cf.json"), encoding="utf-8"))
    base = conf["admin_base"].rstrip("/")
    tok = token()
    os.makedirs(LOCAL, exist_ok=True)
    before = len(os.listdir(LOCAL))
    after_key, wrote = "", 0
    while True:
        req = urllib.request.Request(f"{base}/__admin/export?table=predictions&limit=200&after={urllib.request.quote(after_key)}",
                                     headers={"X-Admin-Token": tok, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r:
            lines = [ln for ln in r.read().decode("utf-8").split("\n") if ln.strip()]
        if not lines:
            break
        for ln in lines:
            row = json.loads(ln)
            p = os.path.join(LOCAL, row["k"] + ".json")
            data = row["body"].encode("utf-8")
            if not os.path.exists(p) or open(p, "rb").read() != data:
                with open(p, "wb") as f:
                    f.write(data)
                wrote += 1
            after_key = row["k"]
        if len(lines) < 200:
            break
    after = len(os.listdir(LOCAL))
    print(f"pred_data 同期(Cloudflare): {before} -> {after} 件（書き込み {wrote}）")
    return 0 if after else 1


if __name__ == "__main__":
    sys.exit(main())
