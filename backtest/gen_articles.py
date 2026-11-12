# -*- coding: utf-8 -*-
"""analyses.py に登録された分析から、記事ページと一覧ページを生成する

★1パスで全部集計する★
  分析ごとに 176,819レースを舐めると、1本増やすたびに待ち時間が伸びる。
  ファイルは1回だけ読み、登録された全分析に同じレースを配る。

★サンプル不足は隠さず「判定不能」と出す★
  数字を出せば記事は埋まるが、読めない数字を載せると
  「検証を全部出す」というこのサイトの前提が崩れる。

出力:
  deploy/data/{slug}/index.html   記事
  deploy/data/index.html は別（gen_data_page.py が作る看板ページ）
  deploy/articles/index.html      記事の一覧
"""
import json
import os
import sys

import analyses
import site_config

SITE = site_config.get()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")
JRA_DATA = os.path.join(ROOT, "backtest", "jra_all.jsonl")
OUTDIR = os.path.join(ROOT, "deploy", "data")
INDEX = os.path.join(ROOT, "deploy", "articles", "index.html")

C = {k: f"var(--{k})" for k in
     ("bg", "panel", "line", "txt", "mute", "dim",
      "green", "red", "yellow", "blue", "purple", "orange")}

# 既に手で作ってある記事。一覧にはこれらも並べる
# ★1本目だけ別扱いにする★
#   「データで見る地方競馬」は総集編で、このサイトが何を根拠に喋っているかの
#   説明を兼ねている。20本の中に並べると初見の人に届かないので、一覧の上に出す。
FEATURED = ("", "データで見る地方競馬",
            "券種ごとの壁、人気薄が割高である証拠、AI予想が市場に負けているという話、"
            "そして試して効かなかった検証6件。<strong>まずこれを読んでください。</strong>")

# ★手書き＋別スクリプトが後入れするカードは、必ずここに載せておく★
#   favorite / birthday / no-edge は各生成器が数字を更新するが、
#   gen_articles を後から回すとカードごと消えていた（順序依存の事故）。
#   ここに置けば「誰が最後に回っても」カードは残る。中央の記事も同格で並べる。
# ★カードの説明文に「揮発する数字」を書かない★
#   ここは手書きなので、データが増えても更新されない。実際
#   「地方176,054レース」と書いたまま実データは178,832レースまで増え、
#   /data/index.html は177,134レースと表示していて**サイト内で食い違った**
#   （2026-07-27）。記録ページに48.5%がハードコードで残っていたのと同じ罠。
#   件数・回収率のような動く数字は書かないか、「17万レース超」のように
#   増えても嘘にならない丸めた表現にする。各ページ側は実測値を出している。
HAND = [
    # ★短文の検証メモ★ 長文記事だけだとサイトが「生きている」状態にならない。
    #   1件=1つの検証済み事実で、効かなかったものも含めて短く出す枠
    #   （backtest/memo_data.json + gen_memo_page.py）。件数は数えず固定文にする
    #   （ここに件数を書くとメモを足すたびに嘘になる。記録ページの48.5%と同じ罠）。
    # 見送り記事（gen_miokuri_article.py が実測して生成。数字はここに書かない）
    ("miokuri/", "AIが「見送り」と言ったレースで何が起きているか",
     "見送り判定の中身を検証データ4万レース超で実測。AIが外しやすいレースを事前に言い当てているか、配当はどれだけ荒れるか。"),
    ("memo/", "検証メモ — 短く、全部出す",
     "効いた因子も、効かなかった因子も、見つけたバグも短く。数字は必ず「どれだけの規模で測ったか」つきで出しています。"),
    ("favorite/", "1番人気は、いつ飛ぶのか",
     "中央13万レース超を単勝オッズと頭数で分解。〜1.5倍の1番人気は複勝89%、5.0〜10だと35%。"),
    ("jra/", "中央 vs 地方", "同じ計算式に通して比較。「荒れやすいのは地方」は人気順の信頼度で見ると逆でした。"),
    ("jusho/", "重賞データ — 過去の傾向で見る",
     "中央の143重賞を人気別・枠順別・脚質別の成績と勝ち馬で。有馬記念の1番人気は複勝55%、など過去データを一覧。"),
    ("no-edge/", "効きそうで効かない — 人気で統制すると全部消える",
     "脚質・追い切り・血統・セリ価格・早生まれ・騎手の調子を実測。生の差はあっても人気でそろえると±2pt以内に。市場は織り込み済み。"),
    ("birthday/", "誕生日馬券を買い続けたら、プラスになるのか",
     "決まった馬番を毎レース買い続けた回収率を地方17万レース超で実測。どの番号でも58〜81%で全部100%未満。必勝の番号は無い。"),
    ("debut/", "新馬戦は「荒れる」のか", "情報が少ないから荒れるはず——実測すると逆でした。"),
    ("skip/", "「見送り」のレースは、本当に見送るべきか",
     "的中率は62%→46%と落ちるのに、ワイドの回収率はどのゾーンでも67〜68%でした。"),
    ("nige/", "逃げ馬は本当に儲かるのか",
     "後付けなら単勝300%超。でもレース前に分かる情報だけで組み直すと、全ゾーンで消えました。市場は逃げそうな馬を織り込み済み。"),
    ("jockey-theory/", "有名騎手の\"買い方セオリー\"をガチ検証",
     "43万騎乗の単勝回収率で判定。控除率を超える本物の妙味はごく一部、「頭から買うな」系はよく当たっていました。"),
]


def score(h):
    if h["ar"] is None:
        return None
    s = 50 + (6 - h["ar"]) * 2
    if h["fpf"] is not None:
        s += (0.5 - h["fpf"]) * 10
    return s


AUX = os.path.join(ROOT, "backtest", "nardata", "aux")


def collect():
    """★補助データは月ごとに読み込む★
    延べ178万頭ぶんを一度に持つとメモリに乗らない。bt_all.jsonl は日付順に
    並んでいるので、月が変わったタイミングでその月の aux だけを差し替える。"""
    objs = [cls() for cls in analyses.ALL]
    races = 0
    cur_ym, aux = None, {}
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            ym = rc["d"][:6]
            if ym != cur_ym:
                cur_ym = ym
                p = os.path.join(AUX, f"{ym}.json")
                aux = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
            rc["aux"] = aux.get(rc["rid"])
            pay = rc.get("pay") or {}
            if "fuku" not in pay:
                continue
            hs = [h for h in rc["h"] if h["rk"] is not None]
            if len(hs) < 5:
                continue
            for h in hs:
                h["sc"] = score(h)
            rk = sorted([h for h in hs if h["sc"] is not None], key=lambda x: -x["sc"])
            if not rk:
                continue
            axis = rk[0]
            races += 1
            for o in objs:
                # ★相手（○▲△）を渡す★ 全券種を組むのに必要。
                #   put() が self._rk から取る。add() の引数を変えると
                #   全サブクラスに波及するので、ここで持たせる。
                o._rk = rk
                o.add(rc, hs, pay, axis)
    return objs, races


def bars(rows, w=680, rowh=34):
    """回収率の横棒。判定不能の行はグレーで、数字を出さない"""
    vals = [r["roi"] for r in rows if r["ok"]] or [1]
    vmax = max(vals) * 1.16
    h = rowh * len(rows) + 8
    p = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    lw = 176
    for i, r in enumerate(rows):
        y = i * rowh + 4
        if r["ok"]:
            bw = max(2, (w - lw - 96) * r["roi"] / vmax)
            col = C["green"] if r["roi"] >= 82 else C["blue"] if r["roi"] >= 78 else C["orange"]
            txt = f'{r["roi"]:.1f}%'
        else:
            bw, col, txt = 2, C["line"], "判定不能"
        p.append(
            f'<text x="0" y="{y+18}" fill="{C["mute"]}" font-size="16" '
            f'font-family="Noto Sans JP,sans-serif">{r["label"]}</text>'
            f'<rect x="{lw}" y="{y+4}" width="{bw:.1f}" height="18" rx="4" fill="{col}"/>'
            f'<text x="{lw+bw+8:.1f}" y="{y+18}" fill="{C["txt"]}" font-size="16" '
            f'font-weight="700" font-family="Noto Sans JP,sans-serif">{txt}</text>')
    p.append("</svg>")
    return "".join(p)


CSS = f"""*{{box-sizing:border-box}}
body{{margin:0;background:{C['bg']};color:{C['txt']};
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.8;-webkit-text-size-adjust:100%}}
a{{color:{C['blue']}}}
.wrap{{max-width:820px;margin:0 auto;padding:24px 18px 72px}}
h1{{font-size:29px;line-height:1.4;margin:8px 0 4px}}
h2{{font-size:22px;line-height:1.4;margin:40px 0 10px;font-weight:700;
  border-left:5px solid {C['yellow']};padding-left:12px}}
.lead{{color:{C['mute']};font-size:17px}}
.panel{{background:{C['panel']};border:1px solid {C['line']};border-radius:12px;
  padding:18px 16px;margin:16px 0}}
.note{{color:{C['mute']};font-size:16px;margin-top:10px}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:16px;min-width:460px}}
th,td{{padding:9px 8px;border-bottom:1px solid {C['line']};text-align:left;white-space:nowrap}}
th{{color:{C['mute']};font-weight:700}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}
.dim{{color:{C['mute']}}}
.y{{color:{C['yellow']};font-weight:700}}
.ad{{margin:22px 0}}.ad:empty{{display:none}}
.card{{display:block;background:{C['panel']};border:1px solid {C['line']};
  border-radius:12px;padding:16px;margin:12px 0;text-decoration:none;color:inherit}}
.card:hover{{border-color:{C['yellow']}}}
.card b{{font-size:19px;display:block;line-height:1.4}}
.card.feat{{border-color:{C['yellow']};border-width:2px;padding:20px 18px}}
.card.feat em{{font-style:normal;color:{C['yellow']};font-weight:700;
  display:block;margin-bottom:4px}}
.card.feat b{{font-size:23px}}
.card span{{color:{C['mute']};display:block;margin-top:4px}}
footer{{margin-top:52px;padding-top:18px;border-top:1px solid {C['line']};
  color:{C['mute']};font-size:16px}}"""

BEACON = """<script>
try{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }catch(e){}
</script>"""


def over100_note(rows):
    """「すべて100%を下回る」を決め打ちしない。

    ★これは一度嘘になった★ 複勝しか出していなかった頃は全区分100%割れが
      事実だった。3連単まで出すようにしたら100%超えの区分が現れ、
      定型文だけが古いまま残って矛盾した（2026-07-29）。
      数字は必ず実測から出す。
    """
    good = [r for r in rows if r["ok"]]
    over = [(r, k, lab) for r in good for k, lab, _p in analyses.BETS
            if r["bets"][k] >= 100]
    if not over:
        return ("<p>ここに出ている回収率は<strong>すべて100%を下回っています</strong>。"
                "条件を選んでも、それだけで勝てるようにはなりません。"
                "当サイトでは43通りの戦略と条件別の総当たりを試し、天井は92.2%でした。</p>")
    # 100%を超えた区分があるときは、その中身（大穴頼みか）まで書く
    li = ""
    for r, k, lab in sorted(over, key=lambda x: -x[0]["bets"][x[1]])[:4]:
        ex1 = r["bets_ex1"][k]
        li += (f"<li>「{r['label']}」の{lab}が<strong>{r['bets'][k]:.1f}%</strong>"
               f"（最高配当1本を除くと{ex1:.1f}%）</li>")
    return (f"<p>この表には<strong>100%を超えている区分があります</strong>。</p>"
            f"<ul>{li}</ul>"
            f"<p>ただし当たりにくい券種の回収率は、<strong>大穴1本で丸ごと決まります</strong>。"
            f"上の括弧内が「最も高い配当を1本だけ除いたときの回収率」で、"
            f"そこで大きく落ちるものは再現性がありません。"
            f"当サイトでは43通りの戦略と条件別の総当たりを試しましたが、"
            f"<strong>安定して100%を超える買い方は見つかっていません</strong>。</p>")


def article_html(o, rows, races):
    # ★複勝だけ出さない★ 複勝は当たりやすいぶん配当が削られ、条件差が潰れて見える。
    #   単勝を並べて初めて「どちらの券種で効くのか」が読める。
    # ★7券種すべてを出す★ 複勝だけだと差が潰れて見える。
    #   買い目の形は analyses.BETS に固定してあり、後から選び直さない。
    over100 = over100_note(rows)
    betcols = "".join(f'<th class="n">{lab}</th>' for _k, lab, _p in analyses.BETS)
    tbl = "".join(
        f'<tr><td>{r["label"]}</td><td class="n">{r["n"]:,}</td>'
        + (f'<td class="n">{r["win"]:.1f}%</td><td class="n">{r["fuku"]:.1f}%</td>'
           + "".join(f'<td class="n">{r["bets"][k]:.1f}%</td>'
                     for k, _l, _p in analyses.BETS)
           if r["ok"] else
           f'<td class="n dim" colspan="{2+len(analyses.BETS)}">判定不能（件数不足）</td>')
        + "</tr>" for r in rows)
    ng = [r for r in rows if not r["ok"]]
    return f"""<title>{o.title} — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<script src="{site_config.asset('core/table.js')}" defer></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{o.question[:110]}">
<meta property="og:type" content="article">
<meta property="og:title" content="{o.title}">
<meta property="og:description" content="{o.question[:110]}">
<meta property="og:url" content="{site_config.url('data/' + o.slug + '/')}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<meta property="og:site_name" content="{SITE['name']}">
<meta name="twitter:card" content="summary_large_image">
<style>{CSS}</style>
<div class="wrap">
{site_config.ad_slot(o.slug + "-top")}
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="/articles/">← 記事一覧</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>

<h1>{o.title}</h1>
<p class="lead">{o.question}</p>

<h2>結果</h2>
<div class="panel">{bars(rows)}</div>
<p>{o.finding(rows)}</p>

<h2>数字の一覧</h2>
<div class="scroll"><table class="zebra sortable">
<tr><th>区分</th><th class="n">レース数</th><th class="n">勝率</th><th class="n">複勝率</th>{betcols}</tr>
{tbl}
</table></div>
{f'<p class="note">※ {len(ng)}区分は件数が{analyses.MIN_N:,}に満たないため、数字を出していません。'
 '少ないサンプルの回収率は大きく振れるためです。</p>' if ng else ''}
{f'<p class="note">{o.note}</p>' if o.note else ''}
{analyses.discussion_of(o.slug)}

<h2>読むときの注意</h2>
{over100}
<p class="note"><strong>回収率は7つの券種すべてで出しています。</strong>
複勝はいちばん当たりやすい＝いちばん配当が削られる券種なので、
条件による差が小さく見えます。複勝で差が無くても、単勝や3連単では
はっきり開いていることがあります。<br>
買い目の形は先に決めて固定してあります（◎＝当サイトの本命、○▲△＝スコア2〜4位）:
単勝◎/複勝◎ 各1点、ワイド・馬連・馬単は◎-○▲△の3点、
3連複は◎絡み3点、3連単は◎1着固定で○▲△を並べ替えた6点。
<strong>集計してから良かった買い方を選ぶことはしません</strong>（それは検証ではなく後知恵の選抜です）。</p>
<p class="note">回収率は必ず「買った全レースを分母」にしています。
的中したレースだけを分母にすると、回収率は簡単に水増しできます。
区分の切り方はこの記事のために決め直したものではなく、
<code>backtest/analyses.py</code> に固定してあります。</p>

<footer>
{SITE['name']} ／ データ出典: 地方競馬全国協会 keiba.go.jp<br>
集計対象 {races:,}レース<br>
本ページは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a>
</footer>
</div>
{BEACON}
"""


def jra_race_count():
    """中央の検証コーパスの実レース数。無ければ0（地方だけの表現に落ちる）。"""
    if not os.path.exists(JRA_DATA):
        return 0
    n = 0
    with open(JRA_DATA, "rb") as f:
        for _ in f:
            n += 1
    return n


def index_html(cards, races, jra):
    fs, ft, fd = FEATURED
    hero = (f'<a class="card feat" href="/data/{fs}">'
            f'<em>はじめに読む</em><b>{ft}</b><span>{fd}</span></a>')
    body = "".join(
        f'<a class="card" href="/data/{slug}"><b>{title}</b><span>{desc}</span></a>'
        for slug, title, desc in cards)
    return f"""<title>記事一覧 — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<script src="{site_config.asset('core/table.js')}" defer></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="地方競馬{races:,}レース＋中央競馬{jra:,}レースの実測にもとづく検証記事の一覧。効かなかった検証も公開しています。">
<meta property="og:type" content="website">
<meta property="og:title" content="記事一覧 — {SITE['name']}">
<meta property="og:description" content="{races:,}レースの実測。効かなかった検証も公開しています。">
<meta property="og:url" content="{site_config.url('articles/')}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<meta name="twitter:card" content="summary_large_image">
<style>{CSS}</style>
<div class="wrap">
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="/">← レース一覧</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>

<h1>記事一覧</h1>
<p class="lead">地方競馬 <strong>{races:,}レース</strong>と中央競馬 <strong>{jra:,}レース</strong>の実測にもとづく検証です。<br>
<strong>効かなかった検証も、そのまま載せています。</strong></p>
{hero}
{site_config.ad_slot("articles-top")}
<h2>ほかの検証</h2>
{body}

<footer>
{SITE['name']} ／ データ出典: 地方競馬全国協会 keiba.go.jp、JRA-VAN Data Lab.<br>
本サイトは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a>
</footer>
</div>
{BEACON}
"""


def main():
    print("集計中（17万レースを1パス・全分析を同時に）...", flush=True)
    objs, races = collect()

    cards = list(HAND)
    for o in objs:
        rows = o.rows()
        if not rows:
            print(f"  スキップ {o.slug}（データなし）")
            continue
        d = os.path.join(OUTDIR, o.slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(article_html(o, rows, races))
        ok = sum(1 for r in rows if r["ok"])
        # 一覧に出す説明文は、結論からタグを抜いたもの
        desc = o.finding(rows).replace("<strong>", "").replace("</strong>", "")
        cards.append((o.slug + "/", o.title, desc))
        print(f"  {o.slug:<12} {len(rows)}区分（判定可 {ok}）")

    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    jra = jra_race_count()
    with open(INDEX, "w", encoding="utf-8", newline="\n") as f:
        f.write(index_html(cards, races, jra))
    print(f"\n記事 {len(objs)}本 + 既存{len(HAND)}本 = 一覧に{len(cards)}本")
    print(f"生成: deploy/articles/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
