# -*- coding: utf-8 -*-
"""AI予想家（人格）の成績ページを生成する

入力: backtest/personas_stats.json（bt_personas.js が生成）
出力: deploy/ai/index.html

★このページの肝★
  SPAIA は「万馬券的中レース」「高回収率レース(350%以上)」という
  勝ったレースだけを並べたタブを持っている。こちらはそれをやらない。
  代わりに **全人格の通期成績を、弱いものも含めて順位つきで出す**。
  さらに train と holdout を並べ、「たまたま良かっただけ」でないことを見せる。
"""
import json, os, sys

import site_config
SITE = site_config.get()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "backtest", "personas_stats.json")
OUT = os.path.join(ROOT, "deploy", "ai", "index.html")

# 色は CSS 変数を参照する。実体は core/theme.css（backtest/theme.py が生成）。
# ★ここで16進を持たない★ ライト/ダークの2系統になったので、
#   各ファイルが色を持つと必ずズレる。コントラスト検証も theme.py に集約した。
C = {k: f"var(--{k})" for k in
     ("bg", "panel", "line", "txt", "mute", "dim",
      "green", "red", "yellow", "blue", "purple", "orange")}


# ★本体モデル（GBM）は別のハーネスで測った値★
#   人格は bt_personas.js が同じ条件で測っているが、GBM は netkeiba の
#   ★人数を本文に手書きしない★ 人格を4つ削除したのに文章だけ「13人格」の
#     ままになっていた。数は必ずデータから出す。
#   出馬表から特徴量を作るため、同じ土俵では回せない。
#   実モデル大規模BT（26,731R・公式入力 / 946R・netkeiba入力）の結果が
#   docs/FACTS.md に残っているので、**出所と条件を明記したうえで**併記する。
#   数字を混ぜて同じ表に並べると比較条件が違うことが伝わらないので、別枠にする。
GBM = {"name": "本命（GBM）",
       "desc": "14特徴量の決定木モデル。このサイトの本体で使っているもの",
       "fuku_lo": 61.7, "fuku_hi": 63.3, "races": 26731,
       "linear": 61.4}

# ★人格アイコン（SVGライン画・自作）★ ユーザーの見本を参考に、拡大縮小・テーマ耐性の
#   ある自前SVGで描く。色は人格ごとに変える。ダークの丸バッジに乗せて明暗どちらでも映える。
ICON = {
    "gbm":     ("#3b82f6", '<rect x="6" y="8" width="12" height="9" rx="2"/><path d="M12 8V5"/><circle cx="12" cy="4" r="1.1"/><circle cx="9.6" cy="12" r="1"/><circle cx="14.4" cy="12" r="1"/><path d="M6 20l3-2 2.5 1.2L17 15"/>'),
    "kinso":   ("#06b6d4", '<circle cx="10.5" cy="10.5" r="5"/><path d="M14.5 14.5L19 19"/><path d="M8.5 11v-1.2M10.5 11V8M12.5 11v-2"/>'),
    "senko":   ("#ef4444", '<path d="M3 12h7M4 8h5M4 16h5"/><path d="M11 5l7 7-7 7" fill="none"/>'),
    "best":    ("#f97316", '<path d="M13 3L6 13h5l-1 8 8-11h-5z"/>'),
    "zenso":   ("#8b5cf6", '<path d="M20 12a8 8 0 1 1-3-6.2"/><path d="M20 4v4h-4"/><path d="M12 8v5M9.6 8H12"/>'),
    "jisseki": ("#eab308", '<path d="M8 4h8v4a4 4 0 0 1-8 0z"/><path d="M8 6H5v1a3 3 0 0 0 3 3M16 6h3v1a3 3 0 0 1-3 3"/><path d="M12 12v4M9 20l1-4h4l1 4z"/>'),
    "tekisei": ("#22c55e", '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.6"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>'),
    "wakaba":  ("#84cc16", '<path d="M12 21v-9"/><path d="M12 13c0-3.3 2.2-5.5 5.5-5.5C17.5 10.8 15.3 13 12 13z"/><path d="M12 14c0-3-2-5-5-5 0 3 2 5 5 5z"/>'),
    "balance": ("#94a3b8", '<path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z"/><circle cx="12" cy="12" r="1.6"/><path d="M12 4.5v4M18.5 8.2l-3.4 2M5.5 8.2l3.4 2M12 19.5v-4M18.5 15.8l-3.4-2M5.5 15.8l3.4-2"/>'),
    "market":  ("#0ea5e9", '<path d="M7 4v16M12 3v18M17 5v14"/><rect x="5.5" y="8" width="3" height="7"/><rect x="10.5" y="6" width="3" height="9"/><rect x="15.5" y="9.5" width="3" height="5"/>'),
    "santan1": ("#dc2626", '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.4"/><circle cx="12" cy="12" r="0.9" fill="currentColor" stroke="none"/><path d="M12 2v2.4M12 19.6V22M2 12h2.4M19.6 12H22"/>'),
    "consensus": ("#0d9488", '<circle cx="8" cy="9.5" r="2.3"/><circle cx="16" cy="9.5" r="2.3"/><circle cx="12" cy="14.5" r="2.3"/><path d="M4.5 18c.6-2 2-3 3.5-3M19.5 18c-.6-2-2-3-3.5-3M8.5 20c.7-1.6 2-2.4 3.5-2.4s2.8.8 3.5 2.4"/>'),
    "ltr": ("#6366f1", '<circle cx="5" cy="7" r="1.6"/><circle cx="5" cy="17" r="1.6"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="8.5" r="1.6"/><circle cx="19" cy="15.5" r="1.6"/><path d="M6.5 7.6L10.4 11M6.4 16.3L10.5 13M13.6 11L17.5 8.9M13.6 13L17.5 15.1"/>'),
}


def pico(pid, size=34):
    color, inner = ICON.get(pid, ("#94a3b8", '<circle cx="12" cy="12" r="7"/>'))
    return (f'<span class="pico" style="--pc:{color};width:{size}px;height:{size}px">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{inner}</svg></span>')


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    rows = d["rows"]
    mk = next(r for r in rows if r["market"])
    plain = [r for r in rows if not r["market"]]
    best = plain[0]
    worst = plain[-1]
    # ROI が最も高い人格（複勝率が一番の人とは限らない、が読みどころ）
    roi_best = max(plain, key=lambda r: r["holdout"]["fukuRoi"])
    # train と holdout の順位がどれだけ一致しているか（過学習していないかの目安）
    tr_order = [r["id"] for r in sorted(plain, key=lambda r: -r["train"]["fuku"])]
    ho_order = [r["id"] for r in sorted(plain, key=lambda r: -r["holdout"]["fuku"])]
    same_top3 = len(set(tr_order[:3]) & set(ho_order[:3]))

    def tr(r, i):
        h, t = r["holdout"], r["train"]
        cls = ' style="color:%s"' % C["yellow"] if r["market"] else ""
        # 比較用(市場)・対照群は詳細ページを作らないのでリンクしない
        has_detail = not r["market"] and not r.get("control")
        name_html = (f'<a href="/ai/{r["id"]}/" style="color:inherit;text-decoration:none;'
                     f'border-bottom:1px dashed var(--mute)"><strong>{r["name"]}</strong></a>'
                     if has_detail else f'<strong>{r["name"]}</strong>')
        # 今週（bt_personas.js の weekly・データ最終日から7日間）。Nが小さい週は
        # 順位が揺れるので件数を必ず併記する。無い場合（開催なし等）は—。
        wk = r.get("weekly") or {}
        wk_html = (f'<strong>{wk["rank"]}位</strong>/{wk["of"]}<br>'
                   f'<small style="color:var(--mute)">複勝{wk["fuku"]:.0f}%・{wk["n"]}R</small>'
                   if wk.get("rank") else "—")
        return (f'<tr{cls}><td class="n">{"—" if r["market"] else i}</td>'
                f'<td>{name_html}<br>'
                f'<small style="color:var(--mute)">{r["desc"]}</small></td>'
                f'<td class="n">{wk_html}</td>'
                f'<td class="n">{t["fuku"]:.1f}%</td>'
                f'<td class="n"><strong>{h["fuku"]:.1f}%</strong></td>'
                f'<td class="n">{h["tanRoi"]:.1f}%</td>'
                f'<td class="n">{h["fukuRoi"]:.1f}%</td></tr>')

    body = "".join(tr(r, i) for i, r in enumerate(
        sorted(rows, key=lambda r: (not r["market"], -r["holdout"]["fuku"])), 0))

    # 今週の期間表示（weekly はデータ最終日から7日間・bt_personas.js が計算）
    wk_any = next((r["weekly"] for r in plain
                   if r.get("weekly", {}).get("rank")), None)
    wk_range = (f'{int(wk_any["from"][4:6])}/{int(wk_any["from"][6:8])}'
                f'〜{int(wk_any["to"][4:6])}/{int(wk_any["to"][6:8])}'
                if wk_any else "直近7日")

    # ★一目で分かる成績ランキング（複勝回収率＝どれだけ取れたか順）★
    #   SPAIA/SPAT4 のように順位を立てて出す。ただし勝ちレースだけの水増しはしない。
    #   基準として市場（人気順）を一番上に置く。人格は control(対照) を除いて並べる。
    rank_rows = [r for r in plain if not r.get("control")]
    rank_rows.sort(key=lambda r: -r["holdout"]["fukuRoi"])

    def card(pos, r, is_mk=False):
        h = r["holdout"]
        badge = "基準" if is_mk else str(pos)
        cls = " mk" if is_mk else (" top" if pos <= 3 else "")
        nm = (f'<a href="/ai/{r["id"]}/" style="color:inherit;text-decoration:none">{r["name"]}</a>'
              if not is_mk and not r.get("control") else r["name"])
        return (f'<div class="rc{cls}"><span class="pos">{badge}</span>'
                f'<span class="nm">{nm}</span>'
                f'<span class="mt"><b>{h["fukuRoi"]:.0f}%</b><small>複勝回収率</small></span>'
                f'<span class="mt"><b>{h["fuku"]:.0f}%</b><small>複勝率</small></span></div>')

    rank_cards = card(0, mk, True) + "".join(
        card(i, r) for i, r in enumerate(rank_rows, 1))

    # ★ペルソナごとの「当てたレース」明細（SPAIA/SPAT4のあれ・ただし分母も見せる）★
    TC = {"11": "帯広", "30": "門別", "35": "盛岡", "36": "水沢", "42": "浦和",
          "43": "船橋", "44": "大井", "45": "川崎", "46": "金沢", "47": "笠松",
          "48": "名古屋", "50": "園田", "51": "姫路", "54": "高知", "55": "佐賀"}
    hit_personas = [r for r in plain if not r.get("control") and r.get("hits")]

    import re as _re

    def clean_name(nm):
        nm = (nm or "").strip()
        # keiba.go.jp の名称末尾に付く切れ端「選抜馬ア」等だけを保守的に落とす。
        #   ★削り過ぎ厳禁★（以前「３歳七選抜馬ア」を「３」まで削って壊した）
        nm = _re.sub(r'選抜馬[ァ-ヶー]*$', '', nm).strip('　 ・')
        return nm or "一般戦"

    # ★フォメAI（1レース10,000円を配分して買い目を組む）★ persona_bets.json を使う
    BETS = json.load(open(os.path.join(ROOT, "backtest", "persona_bets.json"), encoding="utf-8"))
    name2id = {r["name"]: r["id"] for r in BETS["rows"]}
    brow = {r["id"]: r for r in BETS["rows"]}

    def combo_str(b):
        # 券種の組を読みやすく。3連単/馬単は◎→○→▲、他は小さい順に-で。単複は番号のみ。
        c = b["c"]
        if isinstance(c, str):
            return c
        c = [str(x) for x in c]
        if len(c) == 1:
            return c[0]
        if b.get("o"):
            return "→".join(c)
        return "-".join(sorted(c, key=lambda x: int(x)))

    def bet_detail(bets):
        # 買った全点（外れ含む）の配分内訳。タップで開く。
        rows = []
        for b in bets:
            hit = b["r"] > 0
            res = f'<span class="win">→{b["r"]:,}円</span>' if hit else '<span class="miss">×</span>'
            rows.append(
                f'<tr class="{"w" if hit else "l"}"><td>{b["k"]}</td><td>{combo_str(b)}</td>'
                f'<td class="n">{b["s"]:,}円</td><td class="n">{res}</td></tr>')
        return ('<table class="btk"><tr><th>券種</th><th>組</th>'
                '<th class="n">掛け金</th><th class="n">払戻</th></tr>'
                + "".join(rows) + '</table>')

    def bet_card(h, pid=None, persona=None):
        ds = f'{int(h["d"][4:6])}/{int(h["d"][6:8])}'
        ven = TC.get(str(h["tc"]), str(h["tc"]))
        nm = clean_name(h.get("name"))
        roi = h["roi"]
        roicls = " big" if roi >= 1000 else ""
        who = (f'{pico(pid, 22)}<span class="whon">{persona}</span>') if persona else ""
        wins = "・".join(f'{b["k"]}{combo_str(b)}' for b in h["bets"] if b["r"] > 0)
        return (
            f'<div class="hitcard" role="button" tabindex="0">'
            f'<div class="stamp">的中</div>'
            f'<div class="hcbody"><div class="hcmeta">{who}{ds}　{ven}{h["r"]}R</div>'
            f'<div class="hcname">{nm}</div>'
            f'<div class="hcpay">購入 <b>10,000円</b> ▶ 払戻 <b>{h["ret"]:,}円</b>'
            f'<span class="hcsub">的中: {wins}　<span class="tap">▸配分</span></span>'
            f'<div class="hcdetail" hidden>{bet_detail(h["bets"])}</div></div></div>'
            f'<div class="hcroi{roicls}">{roi:,}%</div></div>')

    # AI別タブ：人格アイコンのセレクタ＋その人格の直近の当たり買い目
    bet_personas = [r for r in BETS["rows"] if r.get("hits")]
    psel = "".join(
        f'<button type="button" data-p="{r["id"]}"'
        f'{" aria-pressed=\"true\"" if i == 0 else ""}>{pico(r["id"], 26)}'
        f'<span class="psln">{r["name"]}</span></button>'
        for i, r in enumerate(bet_personas))

    def bet_block(i, r):
        style = r.get("style", "")
        style_html = f'　買い方：<strong>{style}</strong>' if style else ""
        return (
            f'<div class="phits" id="ph_{r["id"]}"{"" if i == 0 else " hidden"}>'
            f'<p class="note">「{r["name"]}」に毎レース10,000円を渡して買い目を組ませたとき、'
            f'<strong>当たった直近{len(r["hits"])}レース</strong>です（新しい順）。'
            f'通期の回収率は<strong>{r["roi"]}%</strong>・的中率{r["hitRate"]}%'
            f'（{r["n"]:,}レース・外れも分母）。{style_html}</p>'
            + "".join(bet_card(h, r["id"]) for h in r["hits"]) + '</div>')
    phits = "".join(bet_block(i, r) for i, r in enumerate(bet_personas))

    # 詳細ページ(/ai/{id}/)を持つのは市場・対照群を除く人格のみ
    srows_have_detail = {r["id"] for r in rows if not r.get("market") and not r.get("control")}

    # ★フォメの成績ランキングは期間別★ 今日/前開催/直近7日/先週/今月/先月/通期
    def frank(pos, r):
        cls = " top" if pos <= 3 and r["n"] else ""
        val = lambda v: f'{v:.0f}%' if r["n"] else '—'
        has_detail = r["id"] in srows_have_detail
        nm = (f'<a href="/ai/{r["id"]}/" style="color:inherit;text-decoration:none">'
              f'{pico(r["id"], 26)}{r["name"]}</a>' if has_detail
              else f'{pico(r["id"], 26)}{r["name"]}')
        return (f'<div class="rc{cls}"><span class="pos">{pos if r["n"] else ""}</span>'
                f'<span class="nm">{nm}</span>'
                f'<span class="mt"><b>{val(r["roi"])}</b><small>回収率</small></span>'
                f'<span class="mt"><b>{val(r["hitRate"])}</b><small>的中率</small></span></div>')

    PORDER = ["today", "yesterday", "week", "lastweek", "month", "lastmonth", "all"]
    periods = BETS["periods"]
    psel_period = "".join(
        f'<button type="button" data-per="{k}"{" aria-pressed=\"true\"" if i == 0 else ""}>'
        f'{periods[k]["label"]}</button>' for i, k in enumerate(PORDER) if k in periods)

    # ★万馬券的中／高回収も期間切替できるように★ bt_persona_bets.js が期間ごとに
    #   フィルタ済みで渡してくる bigByPeriod をそのまま使う（JS側でロジックを再実装しない）。
    #   既定タブは「今日（払戻確定の最新日）」。データが薄い期間はその旨を出す。
    big_by_period = BETS.get("bigByPeriod", {})
    lag = BETS.get("dataLagDays", 0)
    lag_note = (f'<p class="note">※公式データは払戻確定に{lag}日ほどラグがあり、'
                f'今日発走ぶんの結果はまだ反映されていません。表示中の最新確定は{lag}日前分です。</p>'
                if lag and lag >= 1 else "")

    def man_pane(key):
        rows = sorted(big_by_period.get(key, []), key=lambda h: -h["ret"])[:40]
        if not rows:
            return '<p class="note">この期間は該当レースがありません。</p>'
        return "".join(bet_card(h, name2id.get(h["persona"]), h["persona"]) for h in rows)

    def hik_pane(key):
        rows = sorted([h for h in big_by_period.get(key, []) if h["roi"] >= 350],
                       key=lambda h: -h["roi"])[:40]
        if not rows:
            return '<p class="note">この期間は回収率350%以上のレースがありません。</p>'
        return "".join(bet_card(h, name2id.get(h["persona"]), h["persona"]) for h in rows)

    psel_man = "".join(
        f'<button type="button" data-manper="{k}"{" aria-pressed=\"true\"" if i == 0 else ""}>'
        f'{periods[k]["label"]}</button>' for i, k in enumerate(PORDER) if k in periods)
    man_panes = "".join(
        f'<div class="manper" data-manper="{k}"{"" if i == 0 else " hidden"}>{man_pane(k)}</div>'
        for i, k in enumerate(PORDER) if k in periods)
    psel_hik = "".join(
        f'<button type="button" data-hikper="{k}"{" aria-pressed=\"true\"" if i == 0 else ""}>'
        f'{periods[k]["label"]}</button>' for i, k in enumerate(PORDER) if k in periods)
    hik_panes = "".join(
        f'<div class="hikper" data-hikper="{k}"{"" if i == 0 else " hidden"}>{hik_pane(k)}</div>'
        for i, k in enumerate(PORDER) if k in periods)
    prank = "".join(
        f'<div class="prank" data-per="{k}"{"" if i == 0 else " hidden"}>'
        + "".join(frank(j, r) for j, r in enumerate(periods[k]["rows"], 1))
        + (f'<p class="note">{periods[k]["label"]}は該当レースが少なく、'
           f'数字は大きくブレます。安定した通期は右端のタブで。</p>'
           if k in ("today", "yesterday") else "")
        + '</div>'
        for i, k in enumerate(PORDER) if k in periods)
    bets_races = BETS["races"]
    today_label = periods.get("today", {}).get("label", "今日")

    html = f"""<title>AI予想家の成績 — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<script src="{site_config.asset('core/table.js')}" defer></script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="観点の違う{len(rows)}つの予想人格を、地方競馬{d['races']:,}レースで実測。弱い人格も隠さず順位つきで公開しています。">
<meta property="og:type" content="article">
<meta property="og:title" content="AI予想家{len(rows)}人の通信簿 — 市場に勝てたのは何人か">
<meta property="og:description" content="{d['races']:,}レースで実測。答えは{'0人' if best['holdout']['fuku'] < mk['holdout']['fuku'] else '複数'}でした。">
<meta property="og:url" content="{site_config.url('ai/')}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<meta property="og:site_name" content="{SITE['name']}">
<meta name="twitter:card" content="summary_large_image">
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.75;-webkit-text-size-adjust:100%}}
a{{color:var(--blue)}}
.wrap{{max-width:900px;margin:0 auto;padding:24px 18px 72px}}
h1{{font-size:30px;line-height:1.4;margin:8px 0 4px}}
h2{{font-size:23px;line-height:1.4;margin:44px 0 10px;font-weight:700;
  border-left:5px solid var(--yellow);padding-left:12px}}
.lead{{color:var(--mute);font-size:17px}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:16px;min-width:620px}}
th,td{{padding:10px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--mute);font-weight:700}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:18px 16px;margin:16px 0}}
.note{{color:var(--mute);font-size:16px}}
.y{{color:var(--yellow);font-weight:700}}
.r{{color:var(--red);font-weight:700}}
.ad{{margin:22px 0}}.ad:empty{{display:none}}
.ranklist{{margin:12px 0}}
.rc{{display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--line);
  border-radius:10px;margin:6px 0;background:var(--panel)}}
.rc.top{{border-color:var(--yellow)}}
.rc.mk{{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 10%,var(--panel))}}
.rc .pos{{flex:0 0 34px;text-align:center;font-weight:800;font-size:17px;color:var(--mute)}}
.rc.top .pos{{color:var(--yellow)}}
.rc.mk .pos{{color:var(--blue);font-size:14px}}
.rc .nm{{flex:1;font-weight:700}}
.rc .mt{{flex:0 0 74px;text-align:right;line-height:1.15}}
.rc .mt b{{font-size:18px;font-variant-numeric:tabular-nums}}
.rc .mt small{{display:block;color:var(--mute);font-size:14px}}
.psel{{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}}
.psel button{{border:1px solid var(--line);background:var(--panel);color:var(--txt);
  border-radius:999px;padding:6px 13px;font-size:14px;font-weight:700;cursor:pointer}}
.psel button[aria-pressed="true"]{{background:var(--blue);color:#fff;border-color:var(--blue)}}
.hitcard{{display:flex;align-items:center;gap:10px;padding:11px 12px;
  border:1px solid var(--line);border-radius:12px;margin:8px 0;background:var(--panel)}}
.hitcard .stamp{{flex:0 0 auto;align-self:flex-start;font-size:14px;font-weight:800;color:var(--red);
  border:2px solid var(--red);border-radius:6px;padding:1px 5px;letter-spacing:.06em}}
.hitcard .hcbody{{flex:1;min-width:0}}
.hitcard .hcmeta{{color:var(--mute);font-size:14px}}
.hitcard .hcname{{font-size:19px;font-weight:800;line-height:1.3;margin:1px 0 3px;
  color:var(--blue);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.hitcard .hcpay{{font-size:14px}}
.hitcard .hcpay b{{font-variant-numeric:tabular-nums}}
.hitcard .hcsub{{display:block;color:var(--mute);font-size:14px}}
.hitcard .hcroi{{flex:0 0 auto;text-align:right;font-size:22px;font-weight:800;
  color:var(--purple);font-variant-numeric:tabular-nums}}
.hitcard .hcroi.big{{color:var(--red)}}
.hitcard{{cursor:pointer}}
.tap{{color:var(--blue);font-weight:700;margin-left:6px;white-space:nowrap}}
.hcdetail{{margin-top:8px}}
.btk{{width:100%;border-collapse:collapse;font-size:14px;min-width:0}}
.btk th,.btk td{{padding:4px 6px;border-bottom:1px solid var(--line);text-align:left}}
.btk th{{color:var(--mute);font-weight:700}}
.btk td.n,.btk th.n{{text-align:right;font-variant-numeric:tabular-nums}}
.btk tr.l td{{color:var(--mute)}}
.btk .win{{color:var(--green);font-weight:700}}
.btk .miss{{color:var(--mute)}}
.pperiod{{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 14px}}
.pperiod button{{border:1px solid var(--line);background:var(--panel);color:var(--txt);
  border-radius:999px;padding:6px 12px;font-size:14px;font-weight:700;cursor:pointer;white-space:nowrap}}
.pperiod button[aria-pressed="true"]{{background:var(--blue);color:#fff;border-color:var(--blue)}}
.prank[hidden]{{display:none}}
footer{{margin-top:52px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--mute);font-size:16px}}
.aitabs{{position:sticky;top:0;z-index:10;display:flex;gap:2px;background:var(--bg);
  border-bottom:1px solid var(--line);margin:14px -18px 14px;padding:0 12px;overflow-x:auto;
  -webkit-overflow-scrolling:touch}}
.aitabs button{{flex:0 0 auto;border:0;background:none;color:var(--mute);font-size:15px;
  font-weight:700;padding:12px 12px;cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap}}
.aitabs button[aria-pressed="true"]{{color:var(--txt);border-bottom-color:var(--blue)}}
.aipane[hidden]{{display:none}}
.aipane>h2:first-child{{margin-top:8px}}
.pico{{display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;
  color:var(--pc);background:#0b1220;border:1px solid color-mix(in srgb,var(--pc) 45%,#0b1220);
  border-radius:50%;vertical-align:middle}}
.pico svg{{width:66%;height:66%}}
.psel button{{display:inline-flex;align-items:center;gap:6px}}
.psln{{white-space:nowrap}}
.hcmeta .pico{{margin-right:5px}}
.whon{{font-weight:700;color:var(--txt);margin-right:6px}}
.rc .nm .pico{{margin-right:7px}}
</style>
<div class="wrap">
{site_config.ad_slot("ai-top")}
<p><a href="/">← レース一覧</a></p>
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px"><div style="flex:1"></div><button class="themebtn" type="button">☾</button></div>
<h1>AI予想家の成績</h1>
<p class="lead">{len(BETS['rows'])}人のAIに<strong>毎レース10,000円</strong>を渡し、
◎○▲△から<strong>それぞれ違う買い方</strong>（単勝勝負・万馬券狙い・連下広め・ワイド軸・
3連単1点・複勝＋3連複BOXなど）で買い目を組ませて、
地方競馬<strong>{bets_races:,}レース</strong>で実測しました。</p>

<div class="aitabs" id="aitabs">
<button type="button" data-t="man" aria-pressed="true">万馬券的中</button>
<button type="button" data-t="hik">高回収</button>
<button type="button" data-t="ai">AI別成績</button>
<button type="button" data-t="more">くわしく</button>
</div>

<div class="aipane" id="ap_man">
<h2>万馬券的中レース</h2>
<p>全AIの買い目で<strong>払戻が大きかったレース</strong>（10,000円→高額）。払戻・買い目とも
公式確定データによる計算で、レースページの<strong>✅確定印</strong>と同じものです
（2026-08-04以降。それ以前は両者が別計算で、僅差の馬で食い違うことがありました）。
なお<strong>発走前に表示していた暫定印</strong>は、まだ確定していないデータで計算するため
順位が入れ替わることがあります。<strong>ここに載った的中は「事前にこの通り買えた」という意味ではありません</strong>。
既定は「{periods.get('today',{}).get('label','今日')}」、他の期間にも切り替えられます。</p>
{lag_note}
<div class="pperiod">{psel_man}</div>
{man_panes}
</div>

<div class="aipane" id="ap_hik" hidden>
<h2>高回収率レース（350%以上）</h2>
<p>全AIの買い目で<strong>回収率350%以上</strong>だったレースを高い順に。既定は
「{periods.get('today',{}).get('label','今日')}」。</p>
{lag_note}
<div class="pperiod">{psel_hik}</div>
{hik_panes}
</div>

<div class="aipane" id="ap_ai" hidden>
<h2>AI別の成績（回収率順）</h2>
<p>毎レース10,000円ずつ買い続けたときの<strong>回収率</strong>順。分母は買った全レース（外れも含む）。
期間を切り替えられます。</p>
<div class="pperiod" id="pperiod">{psel_period}</div>
{prank}
<p class="note r">買い方はAIごとに違います（本命党・単勝勝負／穴党・万馬券狙い／連下広め／ワイド軸／
3連単1点・一点勝負／複勝＋3連複BOXなど）。各AIの買い方は下の「AI別の当たり買い目」で
名前をタップすると出ます。単純な◎複勝1点なら77.5%まで見込めますが、それでは買い目として
面白みがないので、各AIに尖った性格を持たせています。通期ではどのAIも100%未満。今日など
短い期間はたまたま超えることもありますが、続けると負けます。</p>
<h2 style="margin-top:34px">AI別の当たり買い目</h2>
<p class="note">カードを<strong>タップ</strong>すると、10,000円をどう配分したか（外れ含む全点）が開きます。</p>
<div class="psel">{psel}</div>
{phits}
</div>

<div class="aipane" id="ap_more" hidden>
<h2>結論：市場に勝てたAIはいない</h2>
<div class="panel">
<p style="margin:0;font-size:19px">市場（人気順）の複勝率
<strong style="font-size:26px" class="y">{mk['holdout']['fuku']:.1f}%</strong><br>
最も良かった人格「{best['name']}」
<strong style="font-size:26px">{best['holdout']['fuku']:.1f}%</strong></p>
</div>
<p><strong class="r">◎の複勝で見ても、市場を上回った人格は一つもありません。</strong>
上のフォメ（10,000円配分）はもっと不利で、控除率のぶん回収率はさらに下がります。</p>

<h2 id="tsushinbo">{len(rows)}人格の通信簿（◎複勝）</h2>
<p>holdout（検証用に取り分けた {d['split'][:4]}年以降）の複勝率の順です。
「今週」は{wk_range}の実測（毎朝自動更新・件数が少ない週は順位が大きく揺れます）。</p>
<div class="scroll"><table class="zebra sortable">
<tr><th class="n">順</th><th>人格</th><th class="n">今週</th><th class="n">train複勝率</th>
<th class="n">holdout複勝率</th><th class="n">単勝ROI</th><th class="n">複勝ROI</th></tr>
{body}
</table></div>
<p class="note">※ train は {d['split'][:4]}年より前、holdout はそれ以降。
探索と検証を分けているのは、{len(rows)}人格×複数指標を眺めれば
<strong>偶然良く見えるものが必ず出る</strong>ためです。</p>

<h2>本体モデル（GBM）はどうなのか</h2>
<p>ここまでの{len(rows)}人格は、どれも「1つの指標を1方向に見るだけ」の単純な関数です。
では、実際にこのサイトが使っている<strong>14特徴量の決定木モデル</strong>はどうなのか。</p>
<div class="scroll"><table class="zebra sortable">
<tr><th>モデル</th><th class="n">特徴量の数</th><th class="n">複勝率</th><th class="n">レース数</th></tr>
<tr><td>2特徴量の線形式</td><td class="n">2</td><td class="n">{GBM['linear']:.1f}%</td><td class="n">—</td></tr>
<tr><td><strong>{GBM['name']}</strong></td><td class="n">14</td>
    <td class="n"><strong>{GBM['fuku_lo']:.1f}〜{GBM['fuku_hi']:.1f}%</strong></td>
    <td class="n">{GBM['races']:,}</td></tr>
<tr style="color:var(--yellow)"><td>市場（人気順）</td><td class="n">—</td>
    <td class="n"><strong>{mk['holdout']['fuku']:.1f}%</strong></td>
    <td class="n">{mk['holdout']['n']:,}</td></tr>
</table></div>
<p><strong class="y">特徴量を7倍にしても、複勝率は1〜2ポイントしか動きませんでした。</strong>
そして市場には届いていません。</p>
<p>この表の{len(rows)}人格で最も良かった「{best['name']}」は{best['holdout']['fuku']:.1f}%です。
つまり<strong>単純な人格と、本体の決定木モデルが、ほぼ同じ位置にいます。</strong>
モデルを複雑にしても壁は動かない、というのが実測から言えることです。</p>
<p class="note">※ GBMの数値は別のハーネス（実モデル大規模BT・{GBM['races']:,}レース）で測ったものです。
上の表の{len(rows)}人格とは入力データが異なるため、同じ表には並べていません。
条件が違う数字を並べると、比較できているように見えてしまうためです。</p>

<h2>読みどころ</h2>
<p><strong>① 順位が train と holdout でほぼ変わりません。</strong>
上位3人格のうち<strong class="y">{same_top3}つ</strong>が両方で上位3位に入りました。
人格の強弱は偶然ではなく、実力の差です。</p>

<p><strong>② 当たる人格と、儲かる人格は違います。</strong>
複勝率が最も高いのは「{best['name']}」（{best['holdout']['fuku']:.1f}%）ですが、
複勝回収率が最も高いのは「{roi_best['name']}」（{roi_best['holdout']['fukuRoi']:.1f}%、
複勝率は{roi_best['holdout']['fuku']:.1f}%）でした。
<strong>当たる回数が少なくても、配当が良ければ回収率は上がります。</strong></p>

<p><strong>③ 最下位も載せています。</strong>
「{worst['name']}」は複勝率{worst['holdout']['fuku']:.1f}%、
複勝回収率{worst['holdout']['fukuRoi']:.1f}%でした。
これは失敗ではなく、<strong>その観点が単独では効かないという結果</strong>です。
効かなかったことを消すと、残った数字も信用できなくなります。</p>

<h2>作り方</h2>
<p>各人格は「どの指標を、どちら向きに見るか」だけを宣言した単純な関数です。
複雑な重みづけは入れていません。観点の違いをそのまま比べたいからです。</p>
<p><strong>人気（オッズ）を使う人格は「市場」1つだけ</strong>にしています。
全人格にオッズを混ぜると全員が市場に似てしまい、「観点が違う」という前提が崩れるためです。</p>
<p>回収率は必ず「買った全レースを分母」にしています。
的中したレースだけを分母にすると、回収率は簡単に水増しできます。</p>
<p class="note">人格の定義は <code>core/personas.js</code> の1ファイルだけにあり、
このページの集計にも、レース画面の印にも、<strong>同じファイルが使われています</strong>。
別々に実装すると必ずどこかでズレるためです。</p>
</div>

<footer>
{SITE['name']} ／ データ出典: 地方競馬全国協会 keiba.go.jp（公式データダウンロード）<br>
集計対象 {d['races']:,}レース ／ train〜{d['split'][:4]}年 ／ holdout {d['split'][:4]}年〜<br>
本ページは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a>
</footer>
</div>
<script>
/* 上部タブ：カテゴリ切替（縦長を分ける） */
(function(){{
  var tabs = document.getElementById('aitabs');
  if(tabs) tabs.addEventListener('click', function(e){{
    var b = e.target.closest('button[data-t]'); if(!b) return;
    tabs.querySelectorAll('button').forEach(function(x){{ x.removeAttribute('aria-pressed'); }});
    b.setAttribute('aria-pressed', 'true');
    ['man','hik','ai','more'].forEach(function(t){{
      var p = document.getElementById('ap_' + t); if(p) p.hidden = (t !== b.dataset.t);
    }});
    window.scrollTo(0, 0);
  }});
}})();
/* ペルソナ切替：押した人格の的中レースだけ見せる */
(function(){{
  var sel = document.querySelector('.psel');
  if(!sel) return;
  sel.addEventListener('click', function(e){{
    var b = e.target.closest('button[data-p]'); if(!b) return;
    sel.querySelectorAll('button').forEach(function(x){{ x.removeAttribute('aria-pressed'); }});
    b.setAttribute('aria-pressed', 'true');
    document.querySelectorAll('.phits').forEach(function(x){{ x.hidden = true; }});
    var t = document.getElementById('ph_' + b.dataset.p); if(t) t.hidden = false;
  }});
}})();
/* 期間切替：ランキングを今日/前開催/週/月/通期で入れ替える */
(function(){{
  var pp = document.getElementById('pperiod');
  if(!pp) return;
  pp.addEventListener('click', function(e){{
    var b = e.target.closest('button[data-per]'); if(!b) return;
    pp.querySelectorAll('button').forEach(function(x){{ x.removeAttribute('aria-pressed'); }});
    b.setAttribute('aria-pressed', 'true');
    document.querySelectorAll('.prank').forEach(function(x){{
      x.hidden = (x.dataset.per !== b.dataset.per);
    }});
  }});
}})();
/* 万馬券的中／高回収も同じ期間切替（属性名だけ違う: data-manper / data-hikper） */
(function(){{
  [["manper", ".manper"], ["hikper", ".hikper"]].forEach(function(pair){{
    var attr = pair[0], paneSel = pair[1];
    document.querySelectorAll('.pperiod').forEach(function(sel){{
      if(!sel.querySelector('button[data-' + attr + ']')) return;
      sel.addEventListener('click', function(e){{
        var b = e.target.closest('button[data-' + attr + ']'); if(!b) return;
        sel.querySelectorAll('button').forEach(function(x){{ x.removeAttribute('aria-pressed'); }});
        b.setAttribute('aria-pressed', 'true');
        document.querySelectorAll(paneSel).forEach(function(x){{
          x.hidden = (x.dataset[attr] !== b.dataset[attr]);
        }});
      }});
    }});
  }});
}})();
/* 買い目カードをタップ → 10,000円の配分（外れ含む全点）を開閉 */
(function(){{
  document.addEventListener('click', function(e){{
    var card = e.target.closest('.hitcard'); if(!card) return;
    var d = card.querySelector('.hcdetail'); if(!d) return;
    d.hidden = !d.hidden;
    var tap = card.querySelector('.tap'); if(tap) tap.textContent = d.hidden ? '▸配分' : '▾配分';
  }});
}})();
</script>
<script>
/* アクセス計測（Cookieなし・自前）。失敗しても本体に影響させない */
try{{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }}catch(e){{}}
</script>
"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"生成: {os.path.relpath(OUT, ROOT)}  ({len(html.encode('utf-8'))//1024}KB)")
    print(f"  最良 {best['name']} {best['holdout']['fuku']:.1f}% / 市場 {mk['holdout']['fuku']:.1f}%")
    print(f"  ROI最良 {roi_best['name']} {roi_best['holdout']['fukuRoi']:.1f}%")
    print(f"  train/holdout 上位3の一致 {same_top3}/3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
