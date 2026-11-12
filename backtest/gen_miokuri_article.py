# -*- coding: utf-8 -*-
"""記事「AIが『見送り』と言ったレースで何が起きているか」

★数字はその場で実測する★ 記事に手書きしない。
  現行の地方モデル（C12=LTR＋補助）で holdout 全レースの信頼度(firmO)を計算し、
  tweet.html と同じ閾値（firmO<40=見送り）で2群に分けて配当分布を比べる。
  firmness は verify_fuku_rec.py の移植（=tweet.htmlと同じ式）を再利用する。

出力: deploy/data/miokuri/index.html
使い方: python backtest/gen_miokuri_article.py
"""
import json
import os
import statistics
import sys

import numpy as np
import lightgbm as lgb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
import site_config                                             # noqa: E402
from bt_train_ltr import fval, SPLIT                           # noqa: E402
from verify_fuku_rec import firmness                           # noqa: E402
from eval_bets import pay_single                               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")
MODEL = os.path.join(ROOT, "backtest", "ltr_model.txt")
# ★2026-09-28〜 地方の◎はC12（tweet.htmlと同じ z(LTR)+2.0·z(補助) を LTR の平均/幅に戻した値）★
RES_MODEL = os.path.join(ROOT, "backtest", "ltr_res_model.txt")
C12_K = 2.0


def _z(a):
    sd = a.std()
    return (a - a.mean()) / sd if sd > 0 else a * 0
OUT = os.path.join(ROOT, "deploy", "data", "miokuri", "index.html")
SITE = site_config.get()
PASS_TH = 40      # tweet.html の PASS_TH と同値（変えたら両方変える）


def blank():
    return {"n": 0, "hit3": 0, "retF": 0, "tans": [], "santans": []}


def measure():
    B = lgb.Booster(model_file=MODEL)
    BR = lgb.Booster(model_file=RES_MODEL) if os.path.exists(RES_MODEL) else None
    F = B.feature_name()
    g = {"pass": blank(), "buy": blank()}
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            try:
                rc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rc["d"] < SPLIT:
                continue
            pay = rc.get("pay") or {}
            if not pay.get("tan") or not pay.get("fuku"):
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 6:
                continue
            X = np.array([[fval(h, rc, k) for k in F] for h in hs], float)
            s = B.predict(X)
            if BR is not None:
                comb = _z(s) + C12_K * _z(BR.predict(X))
                sc = comb.std()
                s = s.mean() + s.std() * (comb / sc if sc > 0 else comb * 0)
            order = np.argsort(-s)
            ss = [float(s[i]) for i in order]
            top = hs[order[0]]
            pop = top.get("pop")
            fo = firmness(ss, int(pop) if pop is not None else None)
            st = g["pass"] if (fo or 0) < PASS_TH else g["buy"]
            st["n"] += 1
            v = pay_single(pay.get("fuku"), str(int(top["n"])))
            st["retF"] += v
            st["hit3"] += 1 if v else 0
            if pay.get("tan"):
                st["tans"].append(max(pay["tan"].values()))
            santan = pay.get("santan")
            if isinstance(santan, list) and len(santan) == 2 and isinstance(santan[1], (int, float)):
                st["santans"].append(santan[1])
    return g


def q(a, p):
    return statistics.quantiles(a, n=100)[p - 1] if len(a) >= 100 else None


def main():
    g = measure()
    r = {}
    for k, st in g.items():
        tans, sts = sorted(st["tans"]), sorted(st["santans"])
        r[k] = {
            "n": st["n"],
            "fuku": 100 * st["hit3"] / st["n"],
            "fukuRoi": st["retF"] / st["n"],
            "tan_med": statistics.median(tans),
            "tan_p90": q(tans, 90),
            "tan_man": 100 * sum(1 for x in tans if x >= 10000) / len(tans),
            "st_med": statistics.median(sts),
            "st_p90": q(sts, 90),
            "st_p99": q(sts, 99),
            "st_man10": 100 * sum(1 for x in sts if x >= 100000) / len(sts),
            "st_max": max(sts),
        }
    total = r["pass"]["n"] + r["buy"]["n"]
    share = 100 * r["pass"]["n"] / total

    p, b = r["pass"], r["buy"]
    yen = lambda v: f"{int(v):,}円"

    def row(name, key, fmt):
        return (f'<tr><td>{name}</td><td class="n">{fmt(b[key])}</td>'
                f'<td class="n raw">{fmt(p[key])}</td>'
                f'<td class="n">{p[key]/b[key]:.1f}倍</td></tr>')

    NAV = ('<nav class="snav"><a href="/">レース一覧</a><a href="/ai/">AI予想家</a>'
           '<a href="/record/">予想の記録</a><a href="/articles/">記事</a>'
           '<a href="/db/">データベース</a><a href="/calendar/">重賞カレンダー</a></nav>')
    CSS = """*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:17px;line-height:1.9;-webkit-text-size-adjust:100%}
a{color:var(--blue)}
.wrap{max-width:760px;margin:0 auto;padding:24px 18px 72px}
h1{font-size:28px;line-height:1.4;margin:8px 0 6px}
h2{font-size:22px;margin:44px 0 10px;border-left:5px solid var(--blue);padding-left:12px}
.lead{color:var(--mute)}
.snav{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 18px}
.snav a{border:1px solid var(--line);background:var(--panel);border-radius:999px;
  padding:4px 13px;text-decoration:none;color:var(--mute);font-size:15px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:16px;min-width:560px}
th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mute);font-weight:700;background:var(--panel)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.raw{color:var(--txt);font-weight:700}
.key{background:var(--panel);border-left:4px solid var(--yellow);
  padding:16px 18px;margin:24px 0;border-radius:0 10px 10px 0}
.key b{color:var(--txt)}
.note{color:var(--mute);font-size:15px}
footer{margin-top:52px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--mute);font-size:15px}"""

    html = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIが「見送り」と言ったレースで何が起きているか | {SITE['name']}</title>
<meta name="description" content="AI予想が見送り判定したレースを{total:,}レースで実測。◎複勝率は{b['fuku']:.0f}%→{p['fuku']:.0f}%まで落ち、3連単の中央値は{p['st_med']/b['st_med']:.1f}倍になる。">
<link rel="canonical" href="{site_config.url('data/miokuri/')}">
<meta property="og:title" content="AIが「見送り」と言ったレースで何が起きているか">
<meta property="og:description" content="{total:,}レースの実測。見送りレースでは◎複勝率が{p['fuku']:.0f}%まで落ちる。">
<meta property="og:url" content="{site_config.url('data/miokuri/')}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<link rel="stylesheet" href="/core/theme.css">
<style>{CSS}</style></head><body><div class="wrap">
{NAV}
<h1>AIが「見送り」と言ったレースで何が起きているか</h1>
<p class="lead">「当てられないレースを、当てられないと言う」——このサイトの見送り判定
（信頼度{PASS_TH}未満）が実際に何を弾いているのかを、検証用データ{total:,}レース
（{SPLIT[:4]}年以降・現行モデルで再計算）で測った。</p>
{site_config.ad_slot("miokuri-top")}

<h2>見送りは全体の{share:.0f}%</h2>
<p>AIの信頼度（◎がどれだけ抜けているか＋人気の裏付け）が{PASS_TH}を切ったレースが
「見送り」。全体の<b>{share:.1f}%</b>（{p['n']:,}レース）が該当した。
残り{b['n']:,}レースが「買い対象」側になる。</p>
<div class="scroll"><table>
<tr><th></th><th class="n">買い対象</th><th class="n">見送り</th><th class="n">見送り÷買い</th></tr>
<tr><td>レース数</td><td class="n">{b['n']:,}</td><td class="n raw">{p['n']:,}</td><td class="n">—</td></tr>
<tr><td>◎複勝率</td><td class="n">{b['fuku']:.1f}%</td><td class="n raw">{p['fuku']:.1f}%</td><td class="n">—</td></tr>
<tr><td>◎複勝回収率</td><td class="n">{b['fukuRoi']:.1f}%</td><td class="n raw">{p['fukuRoi']:.1f}%</td><td class="n">—</td></tr>
</table></div>
<p>まず精度: 見送りレースでも無理に◎を立てると複勝率は{p['fuku']:.1f}%まで落ちる
（買い対象は{b['fuku']:.1f}%）。<b>見送り判定は「AIが実際に外しやすいレース」を
事前に言い当てている</b>。</p>

<h2>配当はどれだけ荒れるか</h2>
<div class="scroll"><table>
<tr><th>配当</th><th class="n">買い対象</th><th class="n">見送り</th><th class="n">見送り÷買い</th></tr>
{row("勝ち馬の単勝 中央値", "tan_med", yen)}
{row("勝ち馬の単勝 90%点", "tan_p90", yen)}
{row("単勝万馬券率", "tan_man", lambda v: f"{v:.2f}%")}
{row("3連単 中央値", "st_med", yen)}
{row("3連単 90%点", "st_p90", yen)}
{row("3連単 99%点", "st_p99", yen)}
{row("3連単 10万円超率", "st_man10", lambda v: f"{v:.1f}%")}
</table></div>
<p>3連単の中央値は{yen(b['st_med'])}→{yen(p['st_med'])}と<b>{p['st_med']/b['st_med']:.1f}倍</b>、
10万円超が出る確率は{p['st_man10']/max(0.01,b['st_man10']):.1f}倍。確かに荒れやすい。
ただし正直に言うと<b>「桁違い」ではない</b>——99%点は{yen(b['st_p99'])}→{yen(p['st_p99'])}で
{p['st_p99']/b['st_p99']:.1f}倍、単勝万馬券率はむしろ下がる（見送りは小頭数の混戦に
偏るため、組合せの数自体が少ない）。期間中の最高配当は{yen(p['st_max'])}。</p>

<div class="key"><b>つまり見送り判定の価値は、配当ではなく精度の分離にある。</b>
「AIが外しやすいレース」を事前に言い当てて（複勝率{b['fuku']:.0f}%⇔{p['fuku']:.0f}%）、
勝負から外す。見送りレースで穴を狙って買い続ければ大きい配当は確かに出るが、
控除率25%を超えて勝てる証拠は{SITE['name']}の全検証で一度も出ていない
（<a href="/data/">検証一覧</a>）。逆に「当てにいく」なら、見送りを見送ることが
そのまま複勝率{b['fuku']:.0f}%の土台になる。</div>

<h2>数字の出所</h2>
<p class="note">検証用データ（{SPLIT[:4]}年以降・{total:,}レース）に対し、
本番と同じモデル（順位学習＋補助モデル）と信頼度式で判定を再計算した。
ただし信頼度に入る「◎の人気」は確定人気を使っている。本番の朝の予想はオッズ発表前なので
人気を予測で置いており、本番で見送りになるレースの割合はこの記事より少ない。
配当は keiba.go.jp 公式の確定払戻。判定の閾値（信頼度{PASS_TH}未満）は
本番アプリの見送りバッジと同じ。数字は毎回の再生成で実測し直しており、
この記事に手書きの数字は無い。</p>

<footer>{SITE['name']} — 外れも含めて全予想を<a href="/record/">記録</a>しています。
予想は毎朝オッズ発表前に公開。</footer>
</div></body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"生成: {os.path.relpath(OUT, ROOT)}")
    print(f"  見送り {p['n']:,}R({share:.1f}%) 複勝{p['fuku']:.1f}% 3連単99%点{yen(p['st_p99'])}")
    print(f"  買い   {b['n']:,}R 複勝{b['fuku']:.1f}% 3連単99%点{yen(b['st_p99'])}")


if __name__ == "__main__":
    main()
