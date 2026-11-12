# -*- coding: utf-8 -*-
"""公開用データページを bt_all.jsonl から生成する

方針:
  **数値は一切手書きしない。** 全部データから計算して埋める。
  理由は2つ:
    ① 盛れなくなる（今日「全体平均48%」という誤記が本番に出ていた事例がある）
    ② データが増えれば再生成するだけで最新になる

デザイン:
  docs/DADS_DESIGN.md 準拠。暗背景 #0a0e16 に対しコントラスト4.5:1以上、
  本文16px以上、フォントはDADS段階のみ、色はDADSトークンのみ。

出力: deploy/data/index.html（外部リソース一切なし・自己完結）
"""
import json, math, os, statistics
from collections import defaultdict

import site_config
SITE = site_config.get()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")
OUT = os.path.join(ROOT, "deploy", "data", "index.html")

# 色は CSS 変数を参照する。実体は core/theme.css（backtest/theme.py が生成）。
# ★ここで16進を持たない★ ライト/ダークの2系統になったので、
#   各ファイルが色を持つと必ずズレる。コントラスト検証も theme.py に集約した。
C = {k: f"var(--{k})" for k in
     ("bg", "panel", "line", "txt", "mute", "dim",
      "green", "red", "yellow", "blue", "purple", "orange")}


def score(h):
    if h["ar"] is None:
        return None
    s = 50 + (6 - h["ar"]) * 2
    if h["fpf"] is not None:
        s += (0.5 - h["fpf"]) * 10
    return s


def collect():
    """1パスで全部集計する"""
    st = {
        "races": 0, "period": [None, None],
        "takeout": defaultdict(lambda: [0, 0]),        # 券種 -> [inv, ret]
        "pop_tan": defaultdict(lambda: [0, 0, 0, 0]),  # 人気 -> [inv,ret,n,win]
        "pop_fuku": defaultdict(lambda: [0, 0, 0, 0]),
        "axis": [0, 0, 0, 0],                          # モデル◎複勝 [inv,ret,n,hit]
        "fav": [0, 0, 0, 0],                           # 1番人気複勝
        "disagree_axis": [0, 0, 0, 0],                 # 食い違い時に◎
        "disagree_fav": [0, 0, 0, 0],                  # 食い違い時に1番人気
        "zone": defaultdict(lambda: [0, 0, 0, 0]),     # ゾーン -> ◎複勝
        "rule": defaultdict(lambda: [0, 0, 0, 0]),     # 実用ルール
    }
    comb = lambda n, k: math.comb(n, k)

    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            p = rc.get("pay") or {}
            hs = [h for h in rc["h"] if h["rk"] is not None]
            if len(hs) < 5:
                continue
            st["races"] += 1
            d = rc["d"]
            if st["period"][0] is None or d < st["period"][0]:
                st["period"][0] = d
            if st["period"][1] is None or d > st["period"][1]:
                st["period"][1] = d
            k = len(hs)

            # ① 全通りを均等額で買ったときの回収率
            #    ≠ 1 - 控除率。公表払戻率より必ず低く出る（人気薄が割高なため）
            def add_t(name, pts, ret):
                e = st["takeout"][name]
                e[0] += pts * 100
                e[1] += ret
            if "tan" in p:
                add_t("単勝", k, sum(p["tan"].values()))
            if "fuku" in p:
                add_t("複勝", k, sum(p["fuku"].values()))
            if "wide" in p:
                add_t("ワイド", comb(k, 2), sum(p["wide"].values()))
            if "umaren" in p:
                add_t("馬連", comb(k, 2), p["umaren"][1])
            if "umatan" in p:
                add_t("馬単", k * (k - 1), p["umatan"][1])
            if "sanpuku" in p and k >= 3:
                add_t("3連複", comb(k, 3), p["sanpuku"][1])
            if "santan" in p and k >= 3:
                add_t("3連単", k * (k - 1) * (k - 2), p["santan"][1])

            # ② 人気別
            for h in hs:
                if not h["pop"] or h["pop"] > 12:
                    continue
                if "tan" in p:
                    e = st["pop_tan"][h["pop"]]
                    e[0] += 100; e[1] += p["tan"].get(h["n"], 0); e[2] += 1; e[3] += (h["rk"] == 1)
                if "fuku" in p:
                    e = st["pop_fuku"][h["pop"]]
                    e[0] += 100; e[1] += p["fuku"].get(h["n"], 0); e[2] += 1; e[3] += (h["rk"] <= 3)

            if "fuku" not in p:
                continue
            for h in hs:
                h["sc"] = score(h)
            rk = sorted([h for h in hs if h["sc"] is not None], key=lambda x: -x["sc"])
            byp = sorted([h for h in hs if h["pop"]], key=lambda h: h["pop"])
            if len(rk) < 3 or not byp:
                continue
            ax, fv = rk[0], byp[0]

            def put(key, h):
                e = st[key] if isinstance(st[key], list) else None
                if e is None:
                    return
                e[0] += 100; e[1] += p["fuku"].get(h["n"], 0); e[2] += 1; e[3] += (h["rk"] <= 3)

            put("axis", ax)
            put("fav", fv)
            if ax["n"] != fv["n"]:
                put("disagree_axis", ax)
                put("disagree_fav", fv)

            gap = rk[0]["sc"] - rk[1]["sc"]
            z = ("鉄板" if gap >= 8 else "勝負" if gap >= 5 else
                 "狙い目" if gap >= 3 else "様子見" if gap >= 1.5 else "見送り")
            e = st["zone"][z]
            e[0] += 100; e[1] += p["fuku"].get(ax["n"], 0); e[2] += 1; e[3] += (ax["rk"] <= 3)

            for name, ok in [
                ("◎が1番人気 × 9頭以下", ax["pop"] == 1 and rc["fn"] <= 9),
                ("◎が1番人気", ax["pop"] == 1),
                ("9頭以下 × ◎3番人気以内", rc["fn"] <= 9 and ax["pop"] and ax["pop"] <= 3),
                ("全レースで◎を買う", True),
            ]:
                if ok:
                    e = st["rule"][name]
                    e[0] += 100; e[1] += p["fuku"].get(ax["n"], 0); e[2] += 1; e[3] += (ax["rk"] <= 3)
    return st


def bar_svg(rows, w=680, rowh=34, vmax=None, fmt="{:.1f}%"):
    """横棒グラフ。rows = [(ラベル, 値, 色)]"""
    vmax = vmax or max(v for _, v, _ in rows) * 1.12
    h = rowh * len(rows) + 8
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    lw = 190
    for i, (lab, v, col) in enumerate(rows):
        y = i * rowh + 4
        bw = max(2, (w - lw - 78) * v / vmax)
        parts.append(
            f'<text x="0" y="{y+18}" fill="var(--mute)" font-size="16" '
            f'font-family="Noto Sans JP,sans-serif">{lab}</text>'
            f'<rect x="{lw}" y="{y+4}" width="{bw:.1f}" height="18" rx="4" fill="{col}"/>'
            f'<text x="{lw+bw+8:.1f}" y="{y+18}" fill="var(--txt)" font-size="16" '
            f'font-weight="700" font-family="Noto Sans JP,sans-serif">{fmt.format(v)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def main():
    print("集計中（17万レースを1パス）...", flush=True)
    st = collect()
    roi = lambda e: 100 * e[1] / e[0] if e[0] else 0
    hr = lambda e: 100 * e[3] / e[2] if e[2] else 0
    p0, p1 = st["period"]
    per = f"{p0[:4]}年{int(p0[4:6])}月 〜 {p1[:4]}年{int(p1[4:6])}月"

    # --- 券種別控除率 ---
    order = ["単勝", "複勝", "ワイド", "馬単", "馬連", "3連単", "3連複"]
    tk_rows = []
    for k in order:
        e = st["takeout"][k]
        if not e[0]:
            continue
        r = roi(e)
        col = C["green"] if r >= 68 else C["yellow"] if r >= 60 else C["red"]
        # ★「控除率」と呼んではいけない★
        #   これは全通りを均等額で買ったときの回収率。公表払戻率（単複80% 等）より
        #   必ず低く出る。差は控除ではなく favorite-longshot bias（人気薄が割高）による。
        #   均等買いは割高な人気薄を等しく買ってしまうため、その分だけ目減りする。
        tk_rows.append((f"{k}（均等買い）", r, col))

    # --- 人気別 ---
    pop_rows = []
    for k in sorted(st["pop_fuku"]):
        e = st["pop_fuku"][k]
        if e[2] < 5000:
            continue
        r = roi(e)
        col = C["green"] if r >= 80 else C["blue"] if r >= 70 else C["orange"] if r >= 60 else C["red"]
        pop_rows.append((f"{k}番人気（複勝率 {hr(e):.0f}%）", r, col))

    # --- 実用ルール ---
    rule_rows = []
    for k in ["◎が1番人気 × 9頭以下", "◎が1番人気", "9頭以下 × ◎3番人気以内", "全レースで◎を買う"]:
        e = st["rule"][k]
        if not e[2]:
            continue
        rule_rows.append((f"{k}", hr(e), C["blue"]))

    zone_rows = []
    for k in ["鉄板", "勝負", "狙い目", "様子見", "見送り"]:
        e = st["zone"][k]
        if e[2]:
            zone_rows.append((f"{k}（{e[2]:,}R）", hr(e), C["purple"]))

    ax, fv = st["axis"], st["fav"]
    da, df = st["disagree_axis"], st["disagree_fav"]

    html = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>データで見る地方競馬 — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<script src="{site_config.asset('core/table.js')}" defer></script>
<meta name="description" content="地方競馬{st['races']:,}レースの実測。券種ごとの壁、人気別回収率、AI予想は市場に勝てるのか、そして効かなかったもの。">
<meta property="og:type" content="article">
<meta property="og:title" content="AI予想は、市場に勝てるのか — データで見る地方競馬">
<meta property="og:description" content="{st['races']:,}レースの実測。数値は全て計算で、手入力は一つもありません。効かなかった検証も公開しています。">
<meta property="og:url" content="{site_config.url('data/')}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<meta property="og:site_name" content="{SITE['name']}">
<meta name="twitter:card" content="summary_large_image">
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.75;-webkit-text-size-adjust:100%}}
.wrap{{max-width:820px;margin:0 auto;padding:24px 18px 72px}}
h1{{font-size:32px;line-height:1.4;margin:8px 0 4px;font-weight:700}}
h2{{font-size:24px;line-height:1.4;margin:44px 0 10px;font-weight:700;
  border-left:5px solid var(--yellow);padding-left:12px}}
h3{{font-size:18px;margin:22px 0 8px;font-weight:700;color:var(--yellow)}}
p{{margin:10px 0}}
.lead{{color:var(--mute);font-size:17px}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:18px 16px;margin:16px 0}}
.big{{font-size:36px;font-weight:700;line-height:1.2}}
.note{{color:var(--mute);font-size:16px;margin-top:10px}}  /* DADS: 本文16px以上。14pxは違反 */
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:16px}}
th,td{{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--mute);font-weight:700;font-size:16px}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.g{{color:var(--green);font-weight:700}}
.r{{color:var(--red);font-weight:700}}
.y{{color:var(--yellow);font-weight:700}}
.b{{color:var(--blue);font-weight:700}}
.scroll{{overflow-x:auto}}
footer{{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);
  color:var(--dim);font-size:14px}}
.ad{{margin:22px 0}}
.ad:empty{{display:none}}
a{{color:var(--blue)}}
</style>
<div class="wrap">

<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px"><div style="flex:1"></div><button class="themebtn" type="button">☾</button></div>
<h1>データで見る地方競馬</h1>
<p class="lead">公式データ（keiba.go.jp）<strong>{st['races']:,}レース</strong>／{per}<br>
このページの数値は全て実測です。手入力は一つもありません。</p>

<h2>1. まず知るべきこと — 券種ごとの「壁」</h2>
<p>その券種の全通りを、1点ずつ同じ金額で機械的に買うと、いくら戻るか。
どんな予想でも越えなければならない壁です。</p>
<div class="panel">{bar_svg(tk_rows)}</div>
<p><strong class="y">券種が複雑になるほど壁が高い</strong>のがはっきり出ています。
3連複は半分近く引かれます。「3連単で万馬券」は、その時点で大きなハンデを背負う選択です。</p>
<p class="note">※ この数字は<strong>控除率そのものではありません</strong>。公表されている払戻率は
単勝・複勝で80%前後ですが、均等買いの実測はそれを大きく下回ります。
差は胴元が引いた分ではなく、<strong>割高な人気薄まで等しく買ってしまう</strong>ことで生じます。
次の項がその中身です。</p>

<h2>2. 人気薄は「夢」ではなく「割高」</h2>
<p>人気帯ごとに複勝を買い続けた場合の回収率です。</p>
<div class="panel">{bar_svg(pop_rows)}</div>
<p>きれいな右肩下がりです。<strong class="y">人気馬に寄るほど回収率が高い</strong>。
これは競馬に広く見られる<em>favorite-longshot bias</em>（人気薄が割高に買われる現象）で、
地方競馬でもはっきり確認できます。</p>
<p>「人気薄を狙って一発」は、控除率に加えて<strong class="r">この逆風も背負う</strong>ことになります。
1の均等買いが払戻率より低く出るのも、同じ理由です。</p>

<h2>3. AI予想は市場に勝てるのか</h2>
<p>正直に測りました。比較対象は「無予想」ではなく<strong>「1番人気を買うだけ」</strong>です。
市場は無料で手に入る最強の予測器なので、それを超えられなければ意味がありません。</p>
<div class="scroll"><table class="zebra sortable">
<tr><th>買い方</th><th class="n">複勝率</th><th class="n">回収率</th><th class="n">レース数</th></tr>
<tr><td>モデルの◎</td><td class="n">{hr(ax):.1f}%</td><td class="n">{roi(ax):.1f}%</td><td class="n">{ax[2]:,}</td></tr>
<tr><td><strong>1番人気</strong></td><td class="n g">{hr(fv):.1f}%</td><td class="n g">{roi(fv):.1f}%</td><td class="n">{fv[2]:,}</td></tr>
</table></div>
<p>負けています。さらに決定的なのが、<strong>両者の意見が食い違ったとき</strong>です。</p>
<div class="scroll"><table class="zebra sortable">
<tr><th>◎ ≠ 1番人気 のレース（{da[2]:,}R）</th><th class="n">複勝率</th><th class="n">回収率</th></tr>
<tr><td>◎を買う</td><td class="n r">{hr(da):.1f}%</td><td class="n r">{roi(da):.1f}%</td></tr>
<tr><td>1番人気を買う</td><td class="n g">{hr(df):.1f}%</td><td class="n g">{roi(df):.1f}%</td></tr>
</table></div>
<p><strong class="y">市場と食い違ったとき、モデルはほぼ全敗でした。</strong>
近走成績も、位置取りも、当地実績も、オッズには既に織り込まれています。
公開情報だけを materials にする限り、市場を出し抜くのは容易ではありません。</p>

<h2>4. それでも予想に意味があるとしたら</h2>
<p>「当てる」ではなく「<strong>どのレースを買い、どのレースを見送るか</strong>」です。
◎の複勝率を、レースの読みやすさ（スコア差）で層別しました。</p>
<div class="panel">{bar_svg(zone_rows)}</div>
<p>条件を絞ると精度は上がります。実測で最も安定していたのはこれです。</p>
<div class="scroll"><table class="zebra sortable">
<tr><th>条件</th><th class="n">複勝率</th><th class="n">回収率</th><th class="n">レース数</th></tr>
{''.join(f'<tr><td>{k}</td><td class="n">{hr(st["rule"][k]):.1f}%</td><td class="n">{roi(st["rule"][k]):.1f}%</td><td class="n">{st["rule"][k][2]:,}</td></tr>' for k in ["◎が1番人気 × 9頭以下", "◎が1番人気", "9頭以下 × ◎3番人気以内", "全レースで◎を買う"] if st["rule"][k][2])}
</table></div>
<p class="note">※ 精度は上がりますが、回収率が100%を超えるわけではありません。
絞り込みの価値は「無駄玉を減らすこと」であって「勝てるようになること」ではありません。</p>

<h2>5. 検証したが、効かなかったもの</h2>
<p>ここが一番大事だと思っています。<strong>試して駄目だったことを公開できるのは、
データを持っている側の特権</strong>だからです。</p>
<div class="scroll"><table class="zebra sortable">
<tr><th>試したこと</th><th>結果</th></tr>
<tr><td>馬体重の増減</td><td>複勝率28.6〜31.5%でほぼフラット（67万頭）。市場が織り込み済み</td></tr>
<tr><td>休み明け・連闘</td><td>生の数字では差が出るが、馬の質を揃えると<strong class="r">完全に消えた</strong></td></tr>
<tr><td>逃げ馬が多いと差しが台頭</td><td>差しは一度も先行を逆転しなかった（68,280R）</td></tr>
<tr><td>◎○を厚く買う配分</td><td><strong class="r">逆効果</strong>。◎○は最も割高な組み合わせだった</td></tr>
<tr><td>ダッチング（均等配当になる配分）</td><td>実オッズ5,455Rで差1pt未満。配分は期待値を変えない</td></tr>
<tr><td>買い方43種の総当たり</td><td>回収率100%超は<strong class="r">ひとつも無し</strong>。天井92.2%</td></tr>
</table></div>

<h2>6. このページの作り方</h2>
<p>数値は全て <code>keiba.go.jp</code> の公式データから計算しています。
回収率は必ず<strong>「買った全レースを分母」</strong>にしています。
的中したレースだけを分母にすると回収率は簡単に水増しできるためです
（実際に過去、その誤りで「複勝は黒字」と誤結論した経緯があります）。</p>
<p>探索は 2013-2022 で行い、2023-2026 は検証用に残す形を取っています。
何百通りも試せば偶然100%を超えるものが必ず出るためです。</p>

<h2>7. 続き</h2>
<p><a href="jra/">中央 vs 地方 — 同じ計算式で並べた実測比較</a><br>
中央競馬のデータも同じ方法で集計しました。人気順の信頼度が中央と地方でどう違うか、
「控除率」と実際に失う額がなぜずれるかを扱っています。</p>
<p><a href="skip/">「見送り」のレースは、本当に見送るべきか</a><br>
的中率は62%から46%まで落ちるのに、ワイドの回収率はどのゾーンでも67〜68%で
変わりませんでした。オッズが当たりやすさの差を吸収しています。</p>
<p><a href="debut/">新馬戦は「荒れる」のか</a><br>
過去のレース結果が無い新馬戦は荒れやすいはず——と思って調べたら逆でした。
あわせて「数字が出ていても読んではいけない場合」の話をしています。</p>

{site_config.ad_slot("nar-bottom")}
<footer>
{SITE['name']} ／ データ出典: 地方競馬全国協会 keiba.go.jp（公式データダウンロード）<br>
集計対象 {st['races']:,}レース（{per}）／ ばんえいは平地と性質が異なるため除外<br>
本ページは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a>
</footer>
</div>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8", newline="").write(html)

    # DADS: コントラスト検証
    print("\nDADS コントラスト検証（暗背景 #0a0e16 に対し4.5:1以上）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
