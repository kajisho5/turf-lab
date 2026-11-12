# -*- coding: utf-8 -*-
"""AI予想家（人格）の個別詳細ページを生成する（SITE_MAP P1「人格ごとの詳細ページ」）

入力: backtest/personas_stats.json（train/holdout成績）
      backtest/persona_bets.json（買い目・期間別ランキング・的中履歴）
出力: deploy/ai/{id}/index.html （人格ごとに1ファイル）

★このページの肝★
  /ai/ の一覧はランキングだけ。ここでは1人格に絞り込み、
  ・その人格が何を見ているか（軸の説明）
  ・train/holdout成績（過学習していないかの確認つき）
  ・期間別ランキングでの通期の位置
  ・実際の的中履歴（外れも含む買った全レースが分母、という前提を明記）
  を1ページにまとめる。数を水増ししない・勝ちレースだけ並べない、は一覧と同じ。
"""
import json, os, re, sys

import site_config
SITE = site_config.get()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_STATS = os.path.join(ROOT, "backtest", "personas_stats.json")
SRC_BETS = os.path.join(ROOT, "backtest", "persona_bets.json")
OUT_DIR = os.path.join(ROOT, "deploy", "ai")

# gen_ai_page.py と同じアイコン（片方だけ変えない）
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
BETSTYLE_LABEL = {
    "honmei": "本命党・単勝勝負", "ana": "穴党・万馬券狙い（3連単）",
    "renka": "連下広め（馬連・3連複）", "wide": "ワイド軸で手広く",
    "santan1": "3連単1点・一点勝負", "consensus": "複勝＋3連複BOX（総意）",
}
STYLE_OF = {
    "senko": "honmei", "jisseki": "honmei", "best": "ana", "wakaba": "ana",
    "balance": "renka", "kinso": "renka", "tekisei": "wide", "zenso": "wide",
    "santan1": "santan1", "consensus": "consensus", "ltr": "honmei",
}

TC = {"11": "帯広", "30": "門別", "35": "盛岡", "36": "水沢", "42": "浦和",
      "43": "船橋", "44": "大井", "45": "川崎", "46": "金沢", "47": "笠松",
      "48": "名古屋", "50": "園田", "51": "姫路", "54": "高知", "55": "佐賀"}


def pico(pid, size=34):
    color, inner = ICON.get(pid, ("#94a3b8", '<circle cx="12" cy="12" r="7"/>'))
    return (f'<span class="pico" style="--pc:{color};width:{size}px;height:{size}px">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{inner}</svg></span>')


def clean_name(nm):
    nm = (nm or "").strip()
    nm = re.sub(r'選抜馬[ァ-ヶー]*$', '', nm).strip('　 ・')
    return nm or "一般戦"


def combo_str(b):
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
    rows = []
    for b in bets:
        hit = b["r"] > 0
        res = f'<span class="win">→{b["r"]:,}円</span>' if hit else '<span class="miss">×</span>'
        rows.append(
            f'<tr class="{"w" if hit else "l"}"><td>{b["k"]}</td><td>{combo_str(b)}</td>'
            f'<td class="n">{b["s"]:,}円</td><td class="n">{res}</td></tr>')
    return ('<table class="btk"><tr><th>券種</th><th>組</th>'
            '<th class="n">掛け金</th><th class="n">払戻</th></tr>' + "".join(rows) + '</table>')


def bet_card(h, pid):
    ds = f'{int(h["d"][4:6])}/{int(h["d"][6:8])}'
    ven = TC.get(str(h["tc"]), str(h["tc"]))
    nm = clean_name(h.get("name"))
    roi = h["roi"]
    roicls = " big" if roi >= 1000 else ""
    wins = "・".join(f'{b["k"]}{combo_str(b)}' for b in h["bets"] if b["r"] > 0)
    return (
        f'<div class="hitcard" role="button" tabindex="0">'
        f'<div class="stamp">的中</div>'
        f'<div class="hcbody"><div class="hcmeta">{ds}　{ven}{h["r"]}R</div>'
        f'<div class="hcname">{nm}</div>'
        f'<div class="hcpay">購入 <b>10,000円</b> ▶ 払戻 <b>{h["ret"]:,}円</b>'
        f'<span class="hcsub">的中: {wins}　<span class="tap">▸配分</span></span>'
        f'<div class="hcdetail" hidden>{bet_detail(h["bets"])}</div></div></div>'
        f'<div class="hcroi{roicls}">{roi:,}%</div></div>')


PORDER = ["today", "yesterday", "week", "lastweek", "month", "lastmonth", "all"]


def main():
    stats = json.load(open(SRC_STATS, encoding="utf-8"))
    bets = json.load(open(SRC_BETS, encoding="utf-8"))
    srows = {r["id"]: r for r in stats["rows"]}
    brow = {r["id"]: r for r in bets["rows"]}
    periods = bets["periods"]

    n = 0
    for pid, s in srows.items():
        if s.get("market") or s.get("control"):
            continue   # 比較用・対照群は個別ページを作らない（一覧のみ）
        b = brow.get(pid)
        if not b:
            continue
        h, t = s["holdout"], s["train"]
        mk = srows.get("market", {}).get("holdout", {})

        # 期間別ランキングでの順位
        prank_rows = []
        for k in PORDER:
            if k not in periods:
                continue
            rows_k = periods[k]["rows"]
            pos = next((i for i, r in enumerate(rows_k, 1) if r["id"] == pid), None)
            total = len(rows_k)
            prank_rows.append((periods[k]["label"], pos, total,
                                next((r for r in rows_k if r["id"] == pid), {})))

        prank_html = "".join(
            f'<div class="rc{" top" if pos and pos <= 3 else ""}">'
            f'<span class="pos">{pos if pos else "—"}<small>/{total}</small></span>'
            f'<span class="nm">{label}</span>'
            f'<span class="mt"><b>{row.get("roi", 0):.0f}%</b><small>回収率</small></span>'
            f'<span class="mt"><b>{row.get("hitRate", 0):.0f}%</b><small>的中率</small></span></div>'
            for label, pos, total, row in prank_rows)

        style = STYLE_OF.get(pid, "renka")
        style_label = BETSTYLE_LABEL.get(style, "")

        hits = b.get("hits", [])
        hits_html = "".join(bet_card(hh, pid) for hh in hits) if hits else \
            '<p class="note">直近holdout期間に的中はありません（外れも含めた通期成績は上の表のとおり）。</p>'

        # 過学習チェック（train/holdoutの複勝率差）
        gap = t["fuku"] - h["fuku"]
        gap_note = ("train/holdoutの差はほぼ無く、安定しています。" if abs(gap) < 3 else
                    ("holdoutの方が高く、控えめな結果です。" if gap < 0 else
                     f"trainよりholdoutが{gap:.1f}pt低く、過学習の可能性に注意。"))

        vs_market = "市場にはまだ届いていません" if h["fuku"] < mk.get("fuku", 999) else "市場を上回りました"

        html = f"""<title>{s['name']} — AI予想家の成績詳細 — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{s['name']}（{s['desc']}）の実測成績。holdout複勝率{h['fuku']:.1f}%・買い目回収率{b['roi']}%。{stats['races']:,}レースで検証。">
<meta property="og:type" content="article">
<meta property="og:title" content="{s['name']} — AI予想家の成績詳細">
<meta property="og:description" content="holdout複勝率{h['fuku']:.1f}%・回収率{b['roi']}%（{b['n']:,}レース実測）。{vs_market}。">
<meta property="og:url" content="{site_config.url('ai/' + pid + '/')}">
<meta property="og:site_name" content="{SITE['name']}">
<meta name="twitter:card" content="summary">
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.75;-webkit-text-size-adjust:100%}}
a{{color:var(--blue)}}
.wrap{{max-width:760px;margin:0 auto;padding:24px 18px 72px}}
.hero{{display:flex;align-items:center;gap:14px;margin:8px 0 6px}}
h1{{font-size:26px;line-height:1.35;margin:0}}
.lead{{color:var(--mute);font-size:17px;margin:6px 0 20px}}
h2{{font-size:21px;line-height:1.4;margin:36px 0 10px;font-weight:700;
  border-left:5px solid var(--yellow);padding-left:12px}}
.stylebox{{display:inline-block;background:var(--panel);border:1px solid var(--line);
  border-radius:999px;padding:5px 14px;font-size:14px;font-weight:700;color:var(--mute);margin:4px 0 18px}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:16px}}
th,td{{padding:10px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--mute);font-weight:700}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 16px;margin:16px 0}}
.note{{color:var(--mute);font-size:15px}}
.rc{{display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--line);
  border-radius:10px;margin:6px 0;background:var(--panel)}}
.rc.top{{border-color:var(--yellow)}}
.rc .pos{{flex:0 0 46px;text-align:center;font-weight:800;font-size:16px;color:var(--mute)}}
.rc.top .pos{{color:var(--yellow)}}
.rc .pos small{{display:block;font-size:14px;font-weight:400}}
.rc .nm{{flex:1;font-weight:700;font-size:14px}}
.rc .mt{{flex:0 0 70px;text-align:right;line-height:1.15}}
.rc .mt b{{font-size:17px;font-variant-numeric:tabular-nums}}
.rc .mt small{{display:block;color:var(--mute);font-size:14px}}
.hitcard{{display:flex;align-items:center;gap:10px;padding:11px 12px;
  border:1px solid var(--line);border-radius:12px;margin:8px 0;background:var(--panel);cursor:pointer}}
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
.tap{{color:var(--blue);font-weight:700;margin-left:6px;white-space:nowrap}}
.hcdetail{{margin-top:8px}}
.btk{{width:100%;border-collapse:collapse;font-size:14px}}
.btk th,.btk td{{padding:4px 6px;border-bottom:1px solid var(--line);text-align:left}}
.btk th{{color:var(--mute);font-weight:700}}
.btk td.n,.btk th.n{{text-align:right;font-variant-numeric:tabular-nums}}
.btk tr.l td{{color:var(--mute)}}
.btk .win{{color:var(--green);font-weight:700}}
.btk .miss{{color:var(--mute)}}
.pico{{display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;
  color:var(--pc);background:#0b1220;border:1px solid color-mix(in srgb,var(--pc) 45%,#0b1220);
  border-radius:50%;vertical-align:middle}}
.pico svg{{width:66%;height:66%}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
footer{{margin-top:52px;padding-top:18px;border-top:1px solid var(--line);color:var(--mute);font-size:15px}}
</style>
<div class="wrap">
{site_config.ad_slot("ai-detail-top")}
<p><a href="/ai/">← AI予想家の成績</a></p>
<div class="hero">{pico(pid, 48)}<h1>{s['name']}</h1></div>
<p class="lead">{s['desc']}</p>
<span class="stylebox">買い方：{style_label}</span>

<h2>実測成績</h2>
<div class="scroll"><table>
<tr><th></th><th class="n">train</th><th class="n">holdout</th></tr>
<tr><td>複勝率</td><td class="n">{t['fuku']:.1f}%</td><td class="n"><strong>{h['fuku']:.1f}%</strong></td></tr>
<tr><td>単勝ROI</td><td class="n">—</td><td class="n">{h['tanRoi']:.1f}%</td></tr>
<tr><td>複勝ROI</td><td class="n">—</td><td class="n">{h['fukuRoi']:.1f}%</td></tr>
</table></div>
<p class="note">market（1番人気）のholdout複勝率は{mk.get('fuku', 0):.1f}%。{vs_market}。{gap_note}</p>

<h2>買い目の回収率（10,000円/レース）</h2>
<div class="panel">
<p>「{s['name']}」に毎レース10,000円を渡して{style_label}の買い目を組ませたとき、
通期の回収率は<strong>{b['roi']}%</strong>・的中率<strong>{b['hitRate']}%</strong>
（<strong>{b['n']:,}レース</strong>・外れも分母）。</p>
</div>

<h2>期間別ランキングでの順位</h2>
<div class="ranklist">{prank_html}</div>

<h2>実際の的中（直近{len(hits)}件・新しい順）</h2>
<p class="note">当たったレースだけを都合よく並べているわけではありません。上の通期回収率・的中率が
「買った全レースを分母にした」正直な数字で、ここはその中の的中例です。</p>
{hits_html}

<footer>
<p>集計条件・分母の取り方は<a href="/ai/">AI予想家の成績</a>の一覧ページに準じます。
馬券は20歳から。投資判断は自己責任でお願いします。</p>
</footer>
</div>
"""
        out_path = os.path.join(OUT_DIR, pid, "index.html")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        n += 1

    # ★check_stale.py対策★ OUT_DIR配下のファイルを上書きしただけだとディレクトリの
    #   mtimeは更新されない（新規追加時しか変わらない）ため、「入力より古い」と
    #   誤検知し続ける。ディレクトリのmtimeを明示的に今に更新しておく。
    os.utime(OUT_DIR, None)

    print(f"生成: {n}人格ぶん → deploy/ai/{{id}}/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
