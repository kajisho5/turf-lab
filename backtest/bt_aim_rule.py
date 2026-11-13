# -*- coding: utf-8 -*-
"""狙い目の判定の作り直し（事前登録 PREREG_aim_rule_20261113.md）
  python3 backtest/bt_aim_rule.py fold 2021 / fold 2022 / final <A番号> <q60> <q50>
"""
import sys
_a = sys.argv[1:]
import numpy as np
import bt_battle_rule as B          # 学習・点数の出し方は★勝負の検証と同じものを使う
BATTLE_C = 0.4922


def cands(S, q60, q50):
    bt = [x["fn"] < 14 and x["c"] >= BATTLE_C for x in S]
    ok = lambda x, b: x["fn"] < 14 and not b
    return bt, {
        "A0 今の決まり(点差4以上)": [ok(x, b) and x["gap"] >= 4 for x, b in zip(S, bt)],
        "A1 c 上位2〜4割": [ok(x, b) and x["c"] >= q60 for x, b in zip(S, bt)],
        "A2 c 上位2〜5割": [ok(x, b) and x["c"] >= q50 for x, b in zip(S, bt)],
        "A3 一致+点差4以上": [ok(x, b) and x["agree"] and x["gap"] >= 4 for x, b in zip(S, bt)],
        "A4 一致+c 上位4割": [ok(x, b) and x["agree"] and x["c"] >= q60 for x, b in zip(S, bt)],
        "A5 10頭以下+c 上位5割": [ok(x, b) and x["fn"] <= 10 and x["c"] >= q50 for x, b in zip(S, bt)],
    }


def table(tag, S, q60, q50, only=None):
    bt, C = cands(S, q60, q50)
    B.show(tag + " 全体", S, len(S)); B.show(tag + " ★勝負", [x for x, b in zip(S, bt) if b], len(S))
    for k, m in C.items():
        if only and not (k.startswith("A0") or k.startswith(only + " ")):
            continue
        B.show(tag + " " + k, [x for x, b in zip(S, m) if b], len(S))
        B.show(tag + "   └残り", [x for x, b, t in zip(S, m, bt) if not b and not t], len(S))
    return bt, C


def main():
    rs = B.load(); print("読み込み", len(rs), flush=True)
    if _a[0] == "fold":
        y = _a[1]; lo, hi = y + "0101", str(int(y) + 1) + "0101"
        L, R = B.train(rs, lo); S = [B.signals(r, L, R) for r in rs if lo <= r["d"] < hi]
        c = np.array([x["c"] for x in S]); q60, q50 = float(np.quantile(c, 0.6)), float(np.quantile(c, 0.5))
        print(f"  境目 {y}: 上位4割 q60={q60:.4f} 上位5割 q50={q50:.4f}")
        table(y, S, q60, q50)          # ★この年の境目で表を出す（選抜用）。固定値は2年の平均
        return
    L, R = B.train(rs, "20230101"); S = [B.signals(r, L, R) for r in rs if r["d"] >= "20230101"]
    q60, q50 = float(_a[2]), float(_a[3])
    bt, C = table("最終", S, q60, q50, only=_a[1])
    rng = np.random.default_rng(20261113)
    fuku = np.array([x["fuku"] for x in S], float); tan = np.array([x["tan"] for x in S], float); btm = np.array(bt)
    for key in [k for k in C if k.startswith("A0") or k.startswith(_a[1] + " ")]:
        m = np.array(C[key]); rest = ~m & ~btm
        for yy in ("2023", "2024", "2025", "2026"):
            ym = np.array([x["y"] == yy for x in S])
            print(f"   {key[:2]} {yy}: {int((m&ym).sum()):>5}R 複{fuku[m&ym].mean():5.1f}（全体{fuku[ym].mean():5.1f}・残り{fuku[rest&ym].mean():5.1f}） 単{tan[m&ym].mean():5.1f}（全体{tan[ym].mean():5.1f}）")
        df, dr, dt = [], [], []
        for _ in range(2000):
            i = rng.integers(0, len(S), len(S)); mm = m[i]; rr = rest[i]
            if mm.sum() == 0 or rr.sum() == 0: continue
            df.append(fuku[i][mm].mean() - fuku[i].mean()); dr.append(fuku[i][mm].mean() - fuku[i][rr].mean()); dt.append(tan[i][mm].mean() - tan[i].mean())
        p = lambda v: f"[{np.percentile(v,2.5):+.2f},{np.percentile(v,97.5):+.2f}]"
        print(f"   {key[:2]} 全体との差: 複 {fuku[m].mean()-fuku.mean():+.2f} {p(df)} / 単 {tan[m].mean()-tan.mean():+.2f} {p(dt)} ｜ 残りとの差: 複 {fuku[m].mean()-fuku[rest].mean():+.2f} {p(dr)}")


if __name__ == "__main__":
    main()
