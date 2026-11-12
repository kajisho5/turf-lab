# -*- coding: utf-8 -*-
"""プライバシーポリシー / 免責事項 / お問い合わせ を生成する

★なぜ要るか★
  ① AdSense を入れると **Google が広告用の Cookie を使う**。
     どんなデータが誰に渡るかの明示は避けて通れない。
  ② 審査では運営者情報と連絡先の有無がよく問題になる。
  ③ 自前解析（stats.php）が何を保存し、何を保存しないかを書いておくと、
     「Cookieなし・IP非保存」であることが自分の側の説明にもなる。

★書けないことは書かない★
  住所・氏名・電話番号は本人しか決められない。ここでは連絡手段を
  X(@kaji_keiba) のDMとし、必要になったら追記する形にしている。
  「特定商取引法に基づく表記」は**有料販売を始めるときに必須**になるので、
  そのときに別途作る（無料のうちは対象外）。

出力: deploy/privacy/index.html
"""
import os, sys

import site_config
SITE = site_config.get()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "deploy", "privacy", "index.html")

C = {k: f"var(--{k})" for k in
     ("bg", "panel", "line", "txt", "mute", "dim",
      "green", "red", "yellow", "blue", "purple", "orange")}


def main():
    html = f"""<title>プライバシーポリシー・運営者情報 — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<script src="{site_config.asset('core/table.js')}" defer></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{SITE['name']}のプライバシーポリシー、Cookieの取り扱い、免責事項、運営者情報、お問い合わせ先。">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{C['bg']};color:{C['txt']};
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.85;-webkit-text-size-adjust:100%}}
a{{color:{C['blue']}}}
.wrap{{max-width:760px;margin:0 auto;padding:24px 18px 72px}}
h1{{font-size:28px;line-height:1.4;margin:8px 0 6px}}
h2{{font-size:21px;line-height:1.4;margin:40px 0 8px;font-weight:700;
  border-left:5px solid {C['yellow']};padding-left:12px}}
h3{{font-size:18px;margin:22px 0 4px}}
p,li{{margin:8px 0}}
ul{{padding-left:22px}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:16px}}
th,td{{padding:9px 8px;border-bottom:1px solid {C['line']};text-align:left;vertical-align:top}}
th{{color:{C['mute']};font-weight:700;white-space:nowrap}}
.panel{{background:{C['panel']};border:1px solid {C['line']};border-radius:12px;
  padding:16px;margin:16px 0}}
.note{{color:{C['mute']}}}
footer{{margin-top:52px;padding-top:18px;border-top:1px solid {C['line']};
  color:{C['mute']};font-size:16px}}
</style>
<div class="wrap">
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="/">← レース一覧</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>

<h1>プライバシーポリシー・運営者情報</h1>
<p class="note">最終更新: 2026年7月26日</p>

<div class="panel" style="border-color:{C['yellow']}">
<p><strong>⚠ 馬券（勝馬投票券）を購入できるのは20歳以上の方に限られます。</strong>
20歳未満の方の購入・譲り受けは法律で禁止されています。</p>
<p>ギャンブルは適度に、無理のない範囲で。「やめたくてもやめられない」と感じたら、
一人で抱えず相談窓口へ（相談は無料・秘密は守られます）。</p>
<ul>
<li>依存症対策全国センター「全国の相談窓口・医療機関を探す」：
<a href="https://www.ncasa-japan.jp/you-do/treatment/treatment-map/" target="_blank" rel="noopener">相談先マップ</a></li>
<li>厚生労働省「依存症についてもっと知りたい方へ」：
<a href="https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000149274.html" target="_blank" rel="noopener">依存症ポータル</a></li>
</ul>
</div>

<h2>1. 当サイトが集める情報</h2>

<h3>1-1. アクセス解析（自前・Cookieを使いません）</h3>
<p>どのページが読まれているかを把握するため、独自の仕組みで以下を記録しています。
<strong>外部の解析サービスは利用していません。</strong></p>
<table class="zebra sortable">
<tr><th>記録するもの</th><td>アクセス日時／閲覧したページのパス／参照元のドメイン名／
スマートフォンかPCかの区別</td></tr>
<tr><th>記録しないもの</th><td><strong>Cookieは発行しません。</strong>
IPアドレスは保存しません。ブラウザの識別情報（User-Agent）もそのままでは保存しません。</td></tr>
<tr><th>訪問者数の数え方</th><td>その日限りの値を用いてIPアドレスを不可逆に変換し、
概数のみを数えています。<strong>日付が変わると同じ変換結果にならないため、
日をまたいで同一の方を追跡することはできません。</strong></td></tr>
</table>

<h3>1-2. 広告配信（Google AdSense）</h3>
<div class="panel">
<p>当サイトは第三者配信の広告サービス「Google AdSense」を利用しています。</p>
<ul>
<li>Googleを含む第三者配信事業者は、<strong>Cookie を使用して</strong>、
利用者が当サイトや他のサイトに過去にアクセスした情報にもとづいて広告を配信することがあります。</li>
<li>Googleが広告Cookieを使用することにより、利用者は
<a href="https://adssettings.google.com/authenticated" target="_blank" rel="noopener">広告設定</a>
でパーソナライズ広告を無効にできます。</li>
<li>パーソナライズ広告に使われるCookieを無効にする方法は
<a href="https://www.aboutads.info/choices/" target="_blank" rel="noopener">www.aboutads.info</a>
でも案内されています。</li>
<li>Googleのプライバシーポリシーは
<a href="https://policies.google.com/technologies/ads" target="_blank" rel="noopener">こちら</a>です。</li>
</ul>
<p class="note">※ 広告Cookieは配信事業者が設定するもので、当サイトが内容を取得することはありません。</p>
<p>欧州経済領域（EEA）・英国・スイスからアクセスされた場合は、
Google の同意管理ツールにより<strong>同意の確認画面</strong>が表示されます。
そこで「同意しない」を選ぶこともできます。日本国内からのアクセスでは表示されません。</p>
</div>

<h3>1-3. 外部サイトへのリンク</h3>
<p>当サイトから移動した先のサイトで提供される情報・サービスについては、当サイトは責任を負いません。</p>

<h2>2. 情報の第三者提供</h2>
<p>アクセス解析で記録した情報を、第三者に提供・販売することはありません。
法令にもとづく開示請求があった場合を除きます。</p>

<h2>3. 免責事項</h2>
<div class="panel">
<p><strong>当サイトは情報提供を目的としたものであり、
的中や利益を保証するものではありません。</strong></p>
<ul>
<li>掲載しているデータ・分析結果は、公表されている情報をもとに独自に集計したものです。
正確性・完全性を保証するものではありません。</li>
<li>当サイトの情報にもとづいて行った馬券の購入その他の行為により生じた損害について、
当サイトは一切の責任を負いません。</li>
<li>馬券の購入は20歳以上の方に限られます。無理のない範囲でお楽しみください。</li>
</ul>
<p class="note">当サイトでは、検証の結果として
<strong>「回収率100%を超える買い方は見つかっていない」</strong>ことを
<a href="/about/">このサイトについて</a>および
<a href="/ai/">AI予想家の成績</a>で公開しています。
効かなかった検証も隠さず掲載する方針です。</p>
</div>

<h2>4. 著作権</h2>
<p>当サイトに掲載している文章・図表の著作権は運営者に帰属します。
引用の範囲を超えた無断転載はご遠慮ください。</p>
<p>レース情報については各データ提供元に権利があります。
出典は各ページに明記しています。</p>

<h2>5. 運営者情報・お問い合わせ</h2>
<table class="zebra sortable">
<tr><th>サイト名</th><td>{SITE['name']}（{SITE['base'].split('//')[1]}）</td></tr>
<tr><th>運営</th><td>個人による運営です</td></tr>
<tr><th>お問い合わせ</th><td>X（旧Twitter）
<a href="https://x.com/{SITE['twitter'].lstrip('@')}" target="_blank" rel="noopener">{SITE['twitter']}</a>
のダイレクトメッセージ</td></tr>
</table>
<p class="note">※ 有料サービスを開始する際は、特定商取引法に基づく表記を別途掲載します。</p>

<h2>6. 変更について</h2>
<p>本ポリシーの内容は、必要に応じて予告なく変更することがあります。
変更後の内容は当ページに掲載した時点で効力を生じます。</p>

<footer>
{SITE['name']}<br>
<a href="/">レース一覧</a> ／ <a href="/about/">このサイトについて</a> ／
<a href="/ai/">AI予想家の成績</a>
</footer>
</div>
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
