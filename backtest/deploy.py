# -*- coding: utf-8 -*-
"""本番デプロイ（差分確認 → 承認 → アップロード → 検証）

背景: 2026-07-19 に「サーバー=v355 / パッケージ=v356 / AUDIT=修正済み」の
      三者不一致が起きた。kochi.html は本番で完全に動いていなかったのに
      誰も気づいていなかった。手動FTPだとこれが起きる。

このスクリプトがやること:
  1. サーバーの現物をダウンロードしてハッシュ比較（差分のあるファイルだけ対象に）
  2. 何を上書きするか一覧で表示し、**必ず確認を取る**
  3. sw.js のキャッシュトークン odds-anomaly-vNNN を自動で +1（人間が一番忘れる）
  4. アップロード後、サーバーから取り直してハッシュ検証

使い方:
  python backtest/deploy.py                 # 差分表示のみ（何もアップしない）
  python backtest/deploy.py --push          # 確認プロンプトつきでアップロード
  python backtest/deploy.py --push --yes    # 確認を省略（CI用。手元では使わない）
  python backtest/deploy.py --no-bump       # キャッシュトークンを上げない

認証情報は WinSCP の保存セッションが持っている。このスクリプトは読まないし持たない。
"""
import argparse, hashlib, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINSCP = r"C:\Program Files (x86)\WinSCP\winscp.com"
SESSION = "ftp@seventh-well.com@www1133.onamae.ne.jp"

# ローカル -> リモート の対応。deploy/ と php/ 以外は触らない。
# lab/ は /odds/ とは別階層にコピーが置かれている（共有用）。
MAP = [
    ("deploy/index.html",             "/seventh-well.com/odds/index.html"),
    # 旧 index（ODDS ANOMALY）。使っていないが消さずに退避してある
    ("deploy/anomaly.html",           "/seventh-well.com/odds/anomaly.html"),
    ("deploy/tweet.html",             "/seventh-well.com/odds/tweet.html"),
    # ★2026-07-30: tweet.htmlの地方予想をGBM→LTRに切替（ユーザー指示）★
    #   LTRモデル本体と、公式の馬別成績索引（wr/dr用）を同じ /odds/ 配下へ。
    #   kajikeiba.com側のhorses.jsonはCORSで読めないためlegacyにも置く。
    ("core/ltr_model.js",             "/seventh-well.com/odds/core/ltr_model.js"),
    ("core/ltr_model_t.js",           "/seventh-well.com/odds/core/ltr_model_t.js"),   # 時計つきモデル（mv 2.3）
    ("deploy/data/horses.json",       "/seventh-well.com/odds/data/horses.json"),
    ("deploy/data/nar_index_asof.json", "/seventh-well.com/odds/data/nar_index_asof.json"),   # 索引がいつまでの結果で作られたか（外から鮮度を確かめる用）
    # 実運用の成績表（backtest/scoreboard.py が毎朝作る。運営側だけに置く）
    ("deploy/data/scoreboard.json",    "/seventh-well.com/odds/data/scoreboard.json"),
    ("deploy/data/scoreboard.txt",     "/seventh-well.com/odds/data/scoreboard.txt"),
    ("deploy/data/jra_horses.json",   "/seventh-well.com/odds/data/jra_horses.json"),
    # 天気→馬場見込みの較正表（weather_calibrate.py生成。tweet.htmlの表示用）
    ("deploy/data/going_by_rain.json", "/seventh-well.com/odds/data/going_by_rain.json"),
    # LTR◎の複勝見込み較正表（calib_ltr.py生成。tweet.htmlの表示用）
    ("deploy/data/ltr_calib.json",     "/seventh-well.com/odds/data/ltr_calib.json"),
    # 騎手の事前複勝率（build_jockey_index.py生成。LTRのjkr列に使う＝採点に必要）
    ("deploy/data/jockeys.json",       "/seventh-well.com/odds/data/jockeys.json"),
    ("deploy/data/jra_jockeys.json",   "/seventh-well.com/odds/data/jra_jockeys.json"),
    # 調教師・父の事前複勝率（同上。LTRのtrr/sir列に使う）
    ("deploy/data/trainers.json",      "/seventh-well.com/odds/data/trainers.json"),
    ("deploy/data/jra_trainers.json",  "/seventh-well.com/odds/data/jra_trainers.json"),
    ("deploy/data/sires.json",         "/seventh-well.com/odds/data/sires.json"),
    ("deploy/tweet2.html",            "/seventh-well.com/odds/tweet2.html"),  # 🧪LTRデモ（サンドボックス）
    ("deploy/kochi.html",             "/seventh-well.com/odds/kochi.html"),
    ("deploy/lab.html",               "/seventh-well.com/odds/lab.html"),
    ("deploy/kaiko.html",             "/seventh-well.com/odds/kaiko.html"),
    ("deploy/sw.js",                  "/seventh-well.com/odds/sw.js"),
    ("deploy/lab-sw.js",              "/seventh-well.com/odds/lab-sw.js"),
    ("deploy/scoring_explainer.html", "/seventh-well.com/odds/scoring_explainer.html"),
    # 公開データページ（backtest/gen_data_page.py が生成。手で編集しない）
    ("deploy/data/index.html",        "/seventh-well.com/odds/data/index.html"),
    ("deploy/data/jra/index.html",    "/seventh-well.com/odds/data/jra/index.html"),
    ("deploy/data/ogp.png",           "/seventh-well.com/odds/data/ogp.png"),
    ("deploy/data/jra/ogp.png",       "/seventh-well.com/odds/data/jra/ogp.png"),
    # 共有用の /lab/（index.html は LAB_MAP 側で deploy/index.html から自動生成される。
    #  ここでは PWA 用の付随ファイルだけ配る）
    ("deploy/lab-sw.js",              "/seventh-well.com/lab/lab-sw.js"),
    ("deploy/lab-manifest.json",      "/seventh-well.com/lab/lab-manifest.json"),
    ("deploy/lab-icon-192.png",       "/seventh-well.com/lab/lab-icon-192.png"),
    ("deploy/lab-icon-512.png",       "/seventh-well.com/lab/lab-icon-512.png"),
    ("deploy/lab-apple-180.png",      "/seventh-well.com/lab/lab-apple-180.png"),
]

# 公開サイト kajikeiba.com（フォロワー向け）。site_config.py の public と対応。
# ★ここに置くのは「誰に見られてもいいもの」だけ★
#   予想を作る tweet.html や lab は入れない。
PUBLIC_MAP = [
    ("deploy/index.html",          "/kajikeiba.com/index.html"),      # レース一覧（トップ）
    ("deploy/race.html",           "/kajikeiba.com/race.html"),        # 出馬表・結果
    ("deploy/about/index.html",    "/kajikeiba.com/about/index.html"),
    ("php/proxy.php",              "/kajikeiba.com/proxy.php"),
    ("php/proxy_seed.php",         "/kajikeiba.com/proxy_seed.php"),  # netkeibaブロック時の緊急キャッシュ充填
    ("php/nar_official.php",       "/kajikeiba.com/nar_official.php"),  # 公式データ        # 同一オリジンで叩く
    ("deploy/data/index.html",     "/kajikeiba.com/data/index.html"),
    ("deploy/data/ogp.png",        "/kajikeiba.com/data/ogp.png"),
    ("deploy/data/jra/index.html", "/kajikeiba.com/data/jra/index.html"),
    ("deploy/data/jra/ogp.png",    "/kajikeiba.com/data/jra/ogp.png"),
    ("deploy/data/debut/index.html", "/kajikeiba.com/data/debut/index.html"),
    ("deploy/data/skip/index.html", "/kajikeiba.com/data/skip/index.html"),
    # 検証メモ（短文・gen_memo_page.py）。★このマップに足さないと生成しても
    #   本番に出ない（新規ページを作った時に必ず忘れる。実際404を出した）
    ("deploy/data/memo/index.html", "/kajikeiba.com/data/memo/index.html"),
    ("deploy/data/debut/ogp.png",   "/kajikeiba.com/data/debut/ogp.png"),
    ("deploy/ai/index.html",       "/kajikeiba.com/ai/index.html"),
    ("deploy/ai/kinso/index.html",     "/kajikeiba.com/ai/kinso/index.html"),
    ("deploy/ai/senko/index.html",     "/kajikeiba.com/ai/senko/index.html"),
    ("deploy/ai/best/index.html",      "/kajikeiba.com/ai/best/index.html"),
    ("deploy/ai/zenso/index.html",     "/kajikeiba.com/ai/zenso/index.html"),
    ("deploy/ai/jisseki/index.html",   "/kajikeiba.com/ai/jisseki/index.html"),
    ("deploy/ai/tekisei/index.html",   "/kajikeiba.com/ai/tekisei/index.html"),
    ("deploy/ai/wakaba/index.html",    "/kajikeiba.com/ai/wakaba/index.html"),
    ("deploy/ai/balance/index.html",   "/kajikeiba.com/ai/balance/index.html"),
    ("deploy/ai/santan1/index.html",   "/kajikeiba.com/ai/santan1/index.html"),
    ("deploy/ai/consensus/index.html", "/kajikeiba.com/ai/consensus/index.html"),
    ("deploy/ai/ltr/index.html",       "/kajikeiba.com/ai/ltr/index.html"),
    ("deploy/data/horses.json",    "/kajikeiba.com/data/horses.json"),
    ("deploy/data/jra_horses.json", "/kajikeiba.com/data/jra_horses.json"),
    # ★2026-07-30: 騎手・厩舎・父の事前複勝率（LTRのjkr/trr/sir列）★
    #   これを置かないと /ai/ltr が33列モデルを3列欠損で動かし、
    #   公開しているバックテスト成績と別物になる。
    ("deploy/data/jockeys.json",   "/kajikeiba.com/data/jockeys.json"),
    ("deploy/data/jra_jockeys.json", "/kajikeiba.com/data/jra_jockeys.json"),
    ("deploy/data/trainers.json",  "/kajikeiba.com/data/trainers.json"),
    ("deploy/data/jra_trainers.json", "/kajikeiba.com/data/jra_trainers.json"),
    ("deploy/data/sires.json",     "/kajikeiba.com/data/sires.json"),
    # ★人格の確定印（bt_persona_marks.js 生成・直近35日）★
    #   race_app.js がこれを読み、あるレースでは必ず確定印で表示する。
    #   置き忘れると全レースが「⏳暫定」表示のままになり、/ai/の的中カードと
    #   食い違ったままになる（2026-08-04にユーザーが発見した不一致の再発）。
    ("deploy/data/pmarks.json",    "/kajikeiba.com/data/pmarks.json"),
    ("php/race.php",               "/kajikeiba.com/race.php"),      # サーバー側出力
    ("php/sitemap.php",            "/kajikeiba.com/sitemap.php"),
    # ★sitemap.php が読む静的URL一覧（gen_sitemap_urls.py が PUBLIC_MAP から生成）★
    #   これを上げ忘れると sitemap がフォールバックの6件だけになる
    ("php/sitemap_urls.php",       "/kajikeiba.com/sitemap_urls.php"),
    ("php/stats.php",              "/kajikeiba.com/stats.php"),      # 自前計測
    ("php/stats_view.php",         "/kajikeiba.com/stats_view.php"), # 運営用・非リンク
    ("php/error_log.php",          "/kajikeiba.com/error_log.php"),      # JSエラー収集（core/theme.js参照）
    ("php/errlog_view.php",        "/kajikeiba.com/errlog_view.php"),    # 運営用・非リンク
    ("core/theme.css",             "/kajikeiba.com/core/theme.css"),
    ("core/theme.js",              "/kajikeiba.com/core/theme.js"),
    ("core/table.js",              "/kajikeiba.com/core/table.js"),
    ("core/scoring.js",            "/kajikeiba.com/core/scoring.js"),
    ("core/ltr_model.js",          "/kajikeiba.com/core/ltr_model.js"),
    ("core/personas.js",           "/kajikeiba.com/core/personas.js"),
    ("core/race.css",              "/kajikeiba.com/core/race.css"),
    ("core/race_app.js",           "/kajikeiba.com/core/race_app.js"),
    ("core/netkeiba_past.js",      "/kajikeiba.com/core/netkeiba_past.js"),
    ("core/montecarlo.js",         "/kajikeiba.com/core/montecarlo.js"),
    ("deploy/.htaccess",           "/kajikeiba.com/.htaccess"),
    ("deploy/data/age/index.html", "/kajikeiba.com/data/age/index.html"),
    ("deploy/data/axis-pop/index.html", "/kajikeiba.com/data/axis-pop/index.html"),
    ("deploy/data/dist/index.html", "/kajikeiba.com/data/dist/index.html"),
    ("deploy/data/field/index.html", "/kajikeiba.com/data/field/index.html"),
    ("deploy/data/going/index.html", "/kajikeiba.com/data/going/index.html"),
    ("deploy/data/lead-count/index.html", "/kajikeiba.com/data/lead-count/index.html"),
    ("deploy/data/month/index.html", "/kajikeiba.com/data/month/index.html"),
    ("deploy/data/race-no/index.html", "/kajikeiba.com/data/race-no/index.html"),
    ("deploy/data/runs/index.html", "/kajikeiba.com/data/runs/index.html"),
    ("deploy/data/track/index.html", "/kajikeiba.com/data/track/index.html"),
    ("deploy/data/waku/index.html", "/kajikeiba.com/data/waku/index.html"),
    ("deploy/data/weight/index.html", "/kajikeiba.com/data/weight/index.html"),
    ("deploy/articles/index.html", "/kajikeiba.com/articles/index.html"),
    ("deploy/data/no-edge/index.html", "/kajikeiba.com/data/no-edge/index.html"),
    ("deploy/data/birthday/index.html", "/kajikeiba.com/data/birthday/index.html"),
    ("deploy/data/birthday/combos.json", "/kajikeiba.com/data/birthday/combos.json"),
    ("deploy/data/damsire/index.html", "/kajikeiba.com/data/damsire/index.html"),
    ("deploy/data/jockey/index.html", "/kajikeiba.com/data/jockey/index.html"),
    ("deploy/data/sire/index.html", "/kajikeiba.com/data/sire/index.html"),
    ("deploy/data/trainer/index.html", "/kajikeiba.com/data/trainer/index.html"),
    ("deploy/record/index.html",   "/kajikeiba.com/record/index.html"),
    ("deploy/calendar/index.html", "/kajikeiba.com/calendar/index.html"),
    ("deploy/data/jusho/index.html", "/kajikeiba.com/data/jusho/index.html"),
    ("deploy/data/jusho/data.json", "/kajikeiba.com/data/jusho/data.json"),
    ("deploy/data/favorite/index.html", "/kajikeiba.com/data/favorite/index.html"),
    ("deploy/db/jra/index.html",  "/kajikeiba.com/db/jra/index.html"),
    ("deploy/db/jra/jockey/index.html", "/kajikeiba.com/db/jra/jockey/index.html"),
    ("deploy/db/jra/trainer/index.html", "/kajikeiba.com/db/jra/trainer/index.html"),
    ("deploy/db/jra/owner/index.html", "/kajikeiba.com/db/jra/owner/index.html"),
    ("deploy/db/jra/sire/index.html", "/kajikeiba.com/db/jra/sire/index.html"),
    ("deploy/db/jra/damsire/index.html", "/kajikeiba.com/db/jra/damsire/index.html"),
    ("deploy/db/jra/trainer-homeaway/index.html", "/kajikeiba.com/db/jra/trainer-homeaway/index.html"),
    ("deploy/db/jra/horse/index.html", "/kajikeiba.com/db/jra/horse/index.html"),
    ("deploy/db/jra/horse/detail/index.html", "/kajikeiba.com/db/jra/horse/detail/index.html"),
    ("deploy/db/jra/jockey/detail/index.html", "/kajikeiba.com/db/jra/jockey/detail/index.html"),
    ("deploy/db/jra/j/index.json", "/kajikeiba.com/db/jra/j/index.json"),
    ("deploy/db/jra/trainer/detail/index.html", "/kajikeiba.com/db/jra/trainer/detail/index.html"),
    ("deploy/db/jra/t/index.json", "/kajikeiba.com/db/jra/t/index.json"),
    ("deploy/db/jra/owner/detail/index.html", "/kajikeiba.com/db/jra/owner/detail/index.html"),
    ("deploy/db/jra/o/index.json", "/kajikeiba.com/db/jra/o/index.json"),
    ("deploy/db/jra/sire/detail/index.html", "/kajikeiba.com/db/jra/sire/detail/index.html"),
    ("deploy/db/jra/s/index.json", "/kajikeiba.com/db/jra/s/index.json"),
    ("deploy/db/jra/damsire/detail/index.html", "/kajikeiba.com/db/jra/damsire/detail/index.html"),
    ("deploy/db/jra/ds/index.json", "/kajikeiba.com/db/jra/ds/index.json"),
    ("deploy/db/jra/combo/index.html", "/kajikeiba.com/db/jra/combo/index.html"),
    ("deploy/db/jra/g1/index.html", "/kajikeiba.com/db/jra/g1/index.html"),
    ("deploy/db/jra/breeder/index.html", "/kajikeiba.com/db/jra/breeder/index.html"),
    ("deploy/db/jra/breeder/detail/index.html", "/kajikeiba.com/db/jra/breeder/detail/index.html"),
    ("deploy/db/jra/br/index.json", "/kajikeiba.com/db/jra/br/index.json"),
    ("deploy/data/nige/index.html", "/kajikeiba.com/data/nige/index.html"),
    ("deploy/data/jockey-theory/index.html", "/kajikeiba.com/data/jockey-theory/index.html"),
    ("deploy/db/jra/horses_search.json", "/kajikeiba.com/db/jra/horses_search.json"),

    ("deploy/db/index.html",        "/kajikeiba.com/db/index.html"),
    ("deploy/db/jockey/index.html", "/kajikeiba.com/db/jockey/index.html"),
    ("deploy/db/trainer/index.html","/kajikeiba.com/db/trainer/index.html"),
    ("deploy/db/sire/index.html",   "/kajikeiba.com/db/sire/index.html"),
    ("deploy/db/damsire/index.html","/kajikeiba.com/db/damsire/index.html"),
    ("deploy/db/horse/index.html",  "/kajikeiba.com/db/horse/index.html"),
    ("deploy/db/horses_search.json","/kajikeiba.com/db/horses_search.json"),
    ("deploy/db/horse/detail/index.html",  "/kajikeiba.com/db/horse/detail/index.html"),
    ("deploy/db/jockey/detail/index.html", "/kajikeiba.com/db/jockey/detail/index.html"),
    ("deploy/db/j/index.json",             "/kajikeiba.com/db/j/index.json"),
    ("deploy/db/trainer/detail/index.html", "/kajikeiba.com/db/trainer/detail/index.html"),
    ("deploy/db/t/index.json",             "/kajikeiba.com/db/t/index.json"),
    ("deploy/db/combo/index.html",          "/kajikeiba.com/db/combo/index.html"),
    ("deploy/db/g1/index.html",             "/kajikeiba.com/db/g1/index.html"),
    ("deploy/db/trainer-homeaway/index.html", "/kajikeiba.com/db/trainer-homeaway/index.html"),
    ("deploy/privacy/index.html",  "/kajikeiba.com/privacy/index.html"),
    ("deploy/ads.txt",             "/kajikeiba.com/ads.txt"),
    ("deploy/robots.txt",          "/kajikeiba.com/robots.txt"),
]
# ★/data/ の検証記事は analyses.ALL から自動で登録する★
#   1本作るたびに上の配列へ手で足す運用だったが、必ず忘れる。
#   実際 /data/memo/ は登録漏れで404になり、
#   sitemap.php 側でも公開済み37ページが漏れていた（2026-07-28）。
#   記事の存在の正は analyses.ALL なので、そこから機械的に足す。
try:
    import analyses as _an
    _have = {a for a, _ in PUBLIC_MAP}
    for _cls in _an.ALL:
        _src = f"deploy/data/{_cls.slug}/index.html"
        if _src not in _have and os.path.exists(os.path.join(ROOT, _src)):
            PUBLIC_MAP.append((_src, f"/kajikeiba.com/data/{_cls.slug}/index.html"))
except Exception as _e:          # analyses が読めなくてもデプロイ自体は止めない
    print(f"[警告] 記事の自動登録に失敗: {_e}")


# 馬の個別データ（256袋・約78MB）。一覧だけ作って中身を上げ忘れ、
# 「データベースが見れない」状態にした。ここは手で並べず全部拾う。
PUBLIC_MAP += [(f"deploy/db/h/{b:02x}.json", f"/kajikeiba.com/db/h/{b:02x}.json")
               for b in range(256)
               if os.path.exists(os.path.join(ROOT, f"deploy/db/h/{b:02x}.json"))]

# 中央の馬データ（3代血統＋戦績・256袋）。地方と同じく全部拾う
PUBLIC_MAP += [(f"deploy/db/jra/h/{b:02x}.json", f"/kajikeiba.com/db/jra/h/{b:02x}.json")
               for b in range(256)
               if os.path.exists(os.path.join(ROOT, f"deploy/db/jra/h/{b:02x}.json"))]

PHP_MAP = [(f"php/{n}", f"/seventh-well.com/odds/{n}") for n in [
    "proxy.php", "proxy_seed.php", "predictions.php", "nardata.php", "cleanup.php", "results.php",
    "horse.php", "jockey.php", "bias.php", "oddslog.php", "unzip.php", "unzip_horse.php",
    "error_log.php", "errlog_view.php",   # tweet.htmlのJSエラー収集・運営用ビューア
    "line_push.php",                       # LINE配信の出口（トークンはline_config.phpに分離）
]]


# ---------------------------------------------------------------------------
# 海外FX比較サイト fx-compass.jp（静的サイト）
#   ・ソースは別プロジェクト（Desktop/afi）。ROOT 配下ではないので絶対パスで持つ。
#     deploy.py 本体は os.path.join(ROOT, local) だが、local が絶対なら ROOT は無視される。
#   ・変換なし・ビルドなし。dist の中身をそのまま fx-compass.jp/ 直下へ配る。
#   ・Service Worker 未使用 = sw.js のキャッシュトークン処理とは無関係。
#   ・置き場所の一覧を手で維持すると必ず漏れるので、ディレクトリを丸ごと歩いて作る。
# ---------------------------------------------------------------------------
FXCOMPASS_LOCAL = r"C:\Users\seventhwell-011\Desktop\afi"
FXCOMPASS_REMOTE = "/fx-compass.jp"
FXCOMPASS_MAP = []
for _dp, _dns, _fns in os.walk(FXCOMPASS_LOCAL):
    _dns[:] = [d for d in _dns if not d.startswith(".")]   # .claude 等の作業用は配らない
    for _fn in _fns:
        if _fn.startswith("."):
            continue
        _full = os.path.join(_dp, _fn)
        _rel = os.path.relpath(_full, FXCOMPASS_LOCAL).replace("\\", "/")
        FXCOMPASS_MAP.append((_full, FXCOMPASS_REMOTE + "/" + _rel))
FXCOMPASS_MAP.sort(key=lambda t: t[1])


# ---------------------------------------------------------------------------
# 知人向けサイト /lab/（seventh-well.com/lab/）
#
# ★公開サイトと同じものを、ブランド名だけ変えて置く★
#   ソースを2系統に分けるとコピーになり、必ずズレる（これまで4回やった）。
#   そこで **デプロイ時に文字列を書き換える**方式にする。ソースは1つのまま。
#
# 書き換えるもの:
#   ・サイト内の絶対パス "/xxx" → "/lab/xxx"（/lab/ 配下に置くため）
#   ・カジ競馬 → SW TURF LAB、kajikeiba.com → seventh-well.com/lab
#   ・AdSense タグは落とす（知人向けに広告は出さない）
# ---------------------------------------------------------------------------
LAB_REMOTE = "/seventh-well.com/lab"

# ★LAB_MAP は PUBLIC_MAP から自動で作る★
#   もともと手で並べた別リストだったが、公開側にページを足すたびに
#   lab 側へ足し忘れ、データベース・記事・記録が丸ごと欠けた状態になっていた。
#   「1系統にする」と言いながら**置き場所の一覧だけ2系統**だったのが原因。
#   同じ中身を出すサイトなので、リストも1つから導出する。
#
#   除くもの: ads.txt / robots.txt（広告は出さないし、知人向けなので検索に出す必要もない）
LAB_SKIP = {"deploy/ads.txt", "deploy/robots.txt"}
LAB_MAP = [(local, LAB_REMOTE + remote[len("/kajikeiba.com"):])
           for local, remote in PUBLIC_MAP if local not in LAB_SKIP]

# 置換対象（画像・JSONは触らない）。.htaccess は拡張子が無いので名前で見る
LAB_TEXT_EXT = (".html", ".js", ".css", ".php")
LAB_TEXT_NAMES = (".htaccess",)

LAB_SUBS = [
    # ブランド名
    ("カジ競馬", "SW TURF LAB"),
    ("https://kajikeiba.com", "https://seventh-well.com/lab"),
    ("kajikeiba.com", "seventh-well.com/lab"),
    ('<a class="logo" href="/">カジ<span>競馬</span></a>',
     '<a class="logo" href="/lab/">SW TURF <span>LAB</span></a>'),
]

# 属性やJS文字列の中の絶対パスを /lab/ 配下に寄せる
LAB_PATH_PATTERNS = [
    (r'(href=")/(?!/)', r'\1/lab/'),
    (r'(src=")/(?!/)',  r'\1/lab/'),
    # JS文字列の中の絶対パス。★ここに書いた入口しか書き換わらない★
    #   db/ を入れ忘れていて、lab では馬検索の索引が 404 になっていた。
    #   ディレクトリを増やしたらここにも足す（漏れは build_check で拾う）。
    (r"(['\"`])/(proxy\.php|stats\.php|nar_official\.php|race\.php"
     r"|data/|core/|race/|ai/|about/|privacy/|db/|articles/|record/)", r"\1/lab/\2"),
]
LAB_ADSENSE_RE = re.compile(
    r'<script async src="https://pagead2\.googlesyndication\.com[^>]*></script>\n?')


# ★.htaccess は HTML と書き換え方が違う★
#   サブディレクトリに置くと、RewriteRule の**パターン**は /lab/ からの相対、
#   **置換先**はサイトのルートからの絶対、と基準がズレる。
#   これを機械的に href 置換すると、/lab/foo が /foo に飛ぶなど静かに壊れる。
LAB_HTACCESS_SUBS = [
    # https強制: $1 は /lab/ 以下の部分なので /lab/ を足し直さないと外へ飛ぶ
    ("https://%{HTTP_HOST}/$1", "https://%{HTTP_HOST}/lab/$1"),
    # 置換先はルート基準
    ("/race.php?id=$1", "/lab/race.php?id=$1"),
    ("/sitemap.php", "/lab/sitemap.php"),
    # REQUEST_URI もルート基準
    # 先頭に /lab/ を足すだけ。中の data/horses.json は同じ括弧の中なので触らない
    ("^/(db/", "^/lab/(db/"),
    # 直リンク判定の自サイト名
    ("(www\\.)?kajikeiba\\.com", "(www\\.)?seventh-well\\.com/lab"),
    ("^/cache/", "^/lab/cache/"),
]


def lab_transform(local: str, raw: bytes) -> bytes:
    """/lab/ 向けに書き換える。テキスト以外はそのまま返す"""
    base = os.path.basename(local)
    if base in LAB_TEXT_NAMES:
        s = raw.decode("utf-8", "replace")
        for a, b in LAB_HTACCESS_SUBS:
            s = s.replace(a, b)
        return s.encode("utf-8")
    if not local.endswith(LAB_TEXT_EXT):
        return raw
    s = raw.decode("utf-8", "replace")
    s = LAB_ADSENSE_RE.sub("", s)          # 知人向けに広告は出さない
    for a, b in LAB_SUBS:
        s = s.replace(a, b)
    for pat, rep in LAB_PATH_PATTERNS:
        s = re.sub(pat, rep, s)
    s = s.replace("/lab/lab/", "/lab/")    # 二重付与の保険
    return s.encode("utf-8")


# 書き換え漏れの検出。★置換リストに足し忘れると静かに404になる★
#   実際 db/ を入れ忘れて馬検索の索引が読めない状態で気づかなかった。
#   人間が一覧を維持する限り漏れるので、出力側を機械で見る。
LAB_LEFTOVER = re.compile(r'''(?:href=|src=|fetch\(\s*)['"`](/(?!lab/|/)[a-z][\w.\-/]*)''')

# 意図的に /lab/ へ寄せない絶対パス（実行時ガードで lab では発火しないと確認済み）。
#   core/theme.js の error_log.php 送信は `location.hostname!=='kajikeiba.com'` で
#   即returnするため lab では絶対に呼ばれない（2026-07-26、b3fbc4a）。
LAB_LEFTOVER_IGNORE = {"/error_log.php"}


def lab_leftovers(local: str, data: bytes) -> list:
    base = os.path.basename(local)
    if not (local.endswith(LAB_TEXT_EXT) or base in LAB_TEXT_NAMES):
        return []
    found = set(LAB_LEFTOVER.findall(data.decode("utf-8", "replace")))
    return sorted(found - LAB_LEFTOVER_IGNORE)



# ★ブランド名はサイトごとに分けてある★
#   公開サイト = カジ競馬（kajikeiba.com）
#   知人向け   = SW TURF LAB（seventh-well.com/lab）
#   ソースは常に「カジ競馬」で書き、lab_transform がデプロイ時に置き換える。
#   生成スクリプトに "SW TURF LAB" を直書きすると、
#   **公開サイトに旧ブランドが出る**（gen_jra_page.py で実際に出した）。
#   覚えているだけでは抜けるので、出す直前に機械で見る。
LAB_ONLY_WORDS = ("SW TURF LAB", "seventh-well.com/lab")


def brand_leaks(pairs):
    """public に出してはいけない語が混じっていないか。
    ★公開サイト(kajikeiba.com)行きのファイルだけ検査する★
    legacy(/odds/=SW TURF LAB本体)のファイルは "SW TURF LAB" が正当なので除外。
    これをしないと --site both が legacy の tweet.html 等を誤検知して中止する。"""
    bad = []
    for local, remote in pairs:
        if "/kajikeiba.com/" not in remote:
            continue
        if not local.endswith((".html", ".js", ".css", ".php", ".txt")):
            continue
        lp = os.path.join(ROOT, local)
        if not os.path.exists(lp):
            continue
        txt = open(lp, "rb").read().decode("utf-8", "replace")
        hit = [w for w in LAB_ONLY_WORDS if w in txt]
        if hit:
            bad.append((local, hit))
    return bad


#   2026-07-26: v425(単純カウンタ)からセマンティックバージョニング(X.Y.Z)へ切替。
#   以後はデプロイのたびパッチ番号だけ+1する（4.3.0→4.3.1→…）。
SW_TOKEN = re.compile(r'(odds-anomaly-v)(\d+)\.(\d+)\.(\d+)')


def sha_bytes(b):
    h = hashlib.sha256(); h.update(b); return h.hexdigest()


def sha(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def winscp(commands):
    """WinSCP CLI を叩く。保存セッションの認証情報を使う（こちらは持たない）

    /command ではなく **スクリプトファイル方式** を使う。
    subprocess は引数内の " をエスケープするため /command だと
    `open "ftp@...\\"` のように壊れて渡り、「ホストが見つかりません」になる。
    """
    lines = ["option batch continue", "option confirm off",
             "option transfer binary", f'open "{SESSION}"'] + commands + ["exit"]
    fd, script = tempfile.mkstemp(suffix=".txt", text=True)
    os.close(fd)
    # WinSCP のスクリプトは既定で ANSI 解釈。日本語パスは使わない前提で cp932 で書く
    with open(script, "w", encoding="cp932", errors="replace", newline="\r\n") as f:
        f.write("\n".join(lines))
    try:
        r = subprocess.run([WINSCP, f"/script={script}"],
                           capture_output=True, text=True,
                           encoding="cp932", errors="replace")
        return r.stdout + r.stderr
    finally:
        os.unlink(script)


def fetch_remote(pairs, dest):
    """リモートの現物をまとめて取ってくる。取れなかったものは None 扱い"""
    cmds = []
    for i, (_, remote) in enumerate(pairs):
        cmds.append(f'get -nopermissions "{remote}" "{os.path.normpath(os.path.join(dest, str(i)))}"')
    winscp(cmds)
    return {i: os.path.join(dest, str(i)) for i in range(len(pairs))}


def bump_sw_token():
    """sw.js のキャッシュトークンのパッチ番号を+1（X.Y.Z→X.Y.(Z+1)）。戻り値 (旧, 新) / 変更なしなら None"""
    p = os.path.join(ROOT, "deploy", "sw.js")
    s = open(p, encoding="utf-8").read()
    m = SW_TOKEN.search(s)
    if not m:
        return None
    major, minor, patch = int(m.group(2)), int(m.group(3)), int(m.group(4))
    old = f"v{major}.{minor}.{patch}"
    new_patch = patch + 1
    new = f"v{major}.{minor}.{new_patch}"
    open(p, "w", encoding="utf-8", newline="").write(
        SW_TOKEN.sub(rf"\g<1>{major}.{minor}.{new_patch}", s, count=1))
    return (old, new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="実際にアップロードする")
    ap.add_argument("--yes", action="store_true", help="確認プロンプトを省略")
    ap.add_argument("--no-bump", action="store_true", help="キャッシュトークンを上げない")
    ap.add_argument("--php", action="store_true", help="php/ も対象に含める")
    ap.add_argument("--skip-php-check", action="store_true",
                    help="PHPに差分があっても中止しない（意図的にPHPだけ据え置く時のみ）")
    ap.add_argument("--site", default="public",
                    choices=["public", "legacy", "lab", "both", "fxcompass"],
                    help="どのサイトに出すか（既定=public=kajikeiba.com / fxcompass=fx-compass.jp）")
    args = ap.parse_args()

    pairs = []
    lab_pair_ids = set()
    if args.site == "fxcompass":
        pairs += FXCOMPASS_MAP
    if args.site in ("lab", "both"):
        pairs += LAB_MAP
        lab_pair_ids = {id_ for id_ in LAB_MAP}
    if args.site in ("public", "both"):
        pairs += PUBLIC_MAP
    # ★2026-07-30: --php の付け忘れを機械で止める★
    #   PHP_MAP は --php を明示した時だけアップロード対象になる。付け忘れると
    #   **JSは新項目を送るのにサーバーが白リストで捨てる**という一番気づきにくい
    #   壊れ方をする（実際 mv/oProb/wx/mtp の追加で踏みかけた）。
    #   そこで「差分の確認だけは常に行い、差分があるのに --php が無ければ中止」にする。
    #   追加コストは小さなPHP十数本のダウンロードだけ。
    php_check_only = []
    if args.site in ("legacy", "both"):
        pairs += MAP
        if args.php:
            pairs += PHP_MAP
        else:
            php_check_only = list(PHP_MAP)
            pairs += php_check_only
    elif args.php:
        print("!! --php は legacy 側のみ。--site legacy と併せて使う")
        return 1

    # ★lab_transform が要るのは LAB_MAP 由来のペアだけ★
    #   deploy/lab.html 等（MAP側）は /seventh-well.com/lab/index.html にも配るが、
    #   これは元々SW TURF LAB向けに書かれた素の実体なので変換してはいけない。
    #   remote が "/seventh-well.com/lab" で始まるかどうかだけで判定すると、
    #   このMAP側のlab.htmlまで誤って変換してしまう。
    def is_lab(local, remote):
        return (local, remote) in lab_pair_ids

    tmp = tempfile.mkdtemp(prefix="swdeploy_")
    try:
        print("サーバーの現物を取得中...", flush=True)
        got = fetch_remote(pairs, tmp)

        diffs, same, missing = [], [], []
        for i, (local, remote) in enumerate(pairs):
            lp = os.path.join(ROOT, local)
            if not os.path.exists(lp):
                print(f"  ! ローカルに無い: {local}")
                continue
            lh = sha_bytes(lab_transform(local, open(lp, "rb").read()))                  if is_lab(local, remote) else sha(lp)
            rh = sha(got[i])
            if rh is None:
                missing.append((local, remote))
            elif lh == rh:
                same.append((local, remote))
            else:
                diffs.append((local, remote, os.path.getsize(lp), os.path.getsize(got[i])))

        # ★--php の付け忘れ検査★ 差分があるのに --php が無ければ中止する
        if php_check_only:
            php_diff = [l for (l, r, _a, _b) in diffs if (l, r) in set(php_check_only)]
            php_new = [l for (l, r) in missing if (l, r) in set(php_check_only)]
            if php_diff or php_new:
                print()
                print("!! PHPに差分があるのに --php が指定されていない")
                for l in php_diff + php_new:
                    print(f"   {l}")
                print("   このまま上げると、JSは新しい項目を送るのにサーバーが古いまま")
                print("   （白リストで黙って捨てる）という気づきにくい壊れ方になる。")
                print("   → python backtest/deploy.py --site legacy --php --push")
                print("   PHPを上げたくない場合だけ --skip-php-check を付ける。中止した。")
                if not args.skip_php_check:
                    return 1
            # 検査だけなのでアップロード対象からは外す
            _skip = set(php_check_only)
            diffs = [d for d in diffs if (d[0], d[1]) not in _skip]
            missing = [m for m in missing if m not in _skip]
            same = [s for s in same if s not in _skip]

        if args.site in ("public", "both"):
            leaks = brand_leaks(pairs)
            if leaks:
                print()
                print("!! 公開サイトに lab 用のブランド名が混じっている")
                for local, hit in leaks:
                    print(f"   {local}: {', '.join(hit)}")
                print("   ソースは「カジ競馬」で書くこと（lab へはデプロイ時に変換される）。中止した。")
                return 1

        if any(is_lab(l, r) for l, r in pairs):
            bad = []
            for local, remote in pairs:
                if not is_lab(local, remote):
                    continue
                lp = os.path.join(ROOT, local)
                if not os.path.exists(lp):
                    continue
                lo = lab_leftovers(local, lab_transform(local, open(lp, "rb").read()))
                if lo:
                    bad.append((local, lo))
            if bad:
                print("\n!! /lab/ に寄せられていない絶対パスがある（404になる）")
                for local, lo in bad:
                    print(f"   {local}: {', '.join(lo[:6])}")
                print("   LAB_PATH_PATTERNS に入口を足すこと。中止した。")
                return 1

        print()
        print("=" * 78)
        print(f"一致 {len(same)} / 差分 {len(diffs)} / サーバーに無い {len(missing)}")
        print("=" * 78)
        for local, remote, ls, rs in diffs:
            print(f"  [差分] {local:<32} {rs:>9,}B -> {ls:>9,}B  {remote}")
        for local, remote in missing:
            print(f"  [新規] {local:<32} {'':>9}    -> 新規作成    {remote}")

        if not diffs and not missing:
            print("\n差分なし。デプロイ不要。")
            return 0

        if not args.push:
            print("\n（表示のみ。アップロードするには --push を付ける）")
            return 0

        # ★安全ゲート★ HTML を上げる時は毎回、人が手順を忘れても事故らないよう自動で回す。
        #   check_undefined.js: 2026-07-19 に kochi.html が4回連鎖して壊れた実際の原因
        #   （未定義識別子）を検出する。tweet.html を上げる時は check_scoring_sync.py も
        #   （core/scoring.js との二重管理がズレていないか）。どちらか失敗したら中止する。
        #   ★今回プッシュする分のhtmlだけに絞る★ 引数無しで回すと deploy/*.html 全部を
        #   見てしまい、今回の変更と無関係な既存ファイルの問題（未着手の別件）で
        #   関係ないデプロイまで巻き添えで止まる（実際に race.html/tweet2.html で発生させて確認した）。
        push_targets = [l for l, _, _, _ in diffs] + [l for l, _ in missing]
        html_targets = [l for l in push_targets if l.endswith(".html")]
        # check_undefined.js / check_scoring_sync.py は kajikeiba/odds 専用の検証
        # （scoring.js 等の未定義識別子チェック）。静的サイト fx-compass.jp は対象外なので
        # fxcompass デプロイではこの安全ゲートを回さない（誤検出で全ファイルが止まるため）。
        if html_targets and args.site != "fxcompass":
            print(f"\n安全ゲート: check_undefined.js を実行中... ({len(html_targets)}件)", flush=True)
            r = subprocess.run(["node", os.path.join(ROOT, "backtest", "check_undefined.js")] + html_targets,
                                cwd=ROOT)
            if r.returncode != 0:
                print("!! 未定義の識別子が見つかった。中止した。修正してから再実行すること。")
                return 1
            if "deploy/tweet.html" in push_targets:
                print("安全ゲート: check_scoring_sync.py を実行中...", flush=True)
                r = subprocess.run([sys.executable, os.path.join(ROOT, "backtest", "check_scoring_sync.py")],
                                    cwd=ROOT)
                if r.returncode != 0:
                    print("!! tweet.html と core/scoring.js がズレている。中止した。両方を揃えてから再実行すること。")
                    return 1

        # sw.js のトークンを上げる。ただし sw.js 自体が対象に含まれる場合のみ意味がある
        bumped = None
        # sw.js は legacy(/odds/) の PWA 用。public だけのデプロイでは上げる意味がない
        touches_shell = (args.site in ("legacy", "both")
                         and any(l.endswith((".html", ".js")) for l, _, _, _ in diffs))
        if touches_shell and not args.no_bump:
            bumped = bump_sw_token()
            if bumped:
                print(f"\nキャッシュトークン: {bumped[0]} -> {bumped[1]}")
                # sw.js を差分リストに入れ直す（トークン変更で差分が出たため）
                sw = ("deploy/sw.js", "/seventh-well.com/odds/sw.js")
                if not any(l == sw[0] for l, _, _, _ in diffs):
                    lp = os.path.join(ROOT, sw[0])
                    diffs.append((sw[0], sw[1], os.path.getsize(lp), 0))
                    print("  sw.js をアップロード対象に追加")

        print()
        targets = [(l, r) for l, r, _, _ in diffs] + missing
        print(f"アップロードするファイル: {len(targets)}件")
        for l, r in targets:
            print(f"  {l}  ->  {r}")

        if not args.yes:
            print()
            ans = input("本番に反映する。よろしいか [yes/N]: ").strip().lower()
            if ans != "yes":
                print("中止した。")
                return 1

        print("\nアップロード中...", flush=True)
        # ★lab は書き換えたものを送る★ 元ファイルは触らない（ソースは1系統のまま）
        send = tempfile.mkdtemp(prefix="swlab_")
        cmds = []
        for i, (l, r) in enumerate(targets):
            src = os.path.normpath(os.path.join(ROOT, l))
            if is_lab(l, r):
                out = os.path.join(send, f"{i}_" + os.path.basename(l))
                with open(out, "wb") as f:
                    f.write(lab_transform(l, open(src, "rb").read()))
                src = out
            cmds.append(f'put -nopermissions "{src}" "{r}"')
        out = winscp(cmds)
        done = out.count("100%")
        if done < len(targets):
            print(out[-2000:])
            print(f"!! 転送完了は {done}/{len(targets)} 件。上の出力を確認する。")
            return 1

        # 検証: 取り直してハッシュ比較
        print("検証中（サーバーから取り直して照合）...", flush=True)
        vdir = tempfile.mkdtemp(prefix="swverify_")
        try:
            vgot = fetch_remote(targets, vdir)
            ng = 0
            for i, (l, r) in enumerate(targets):
                lp2 = os.path.join(ROOT, l)
                lh = sha_bytes(lab_transform(l, open(lp2, "rb").read()))                      if is_lab(l, r) else sha(lp2)
                rh = sha(vgot[i])
                ok = (lh == rh)
                print(f"  {'OK ' if ok else 'NG '} {l}")
                if not ok:
                    ng += 1
            if ng:
                print(f"\n!! {ng}件が一致しない。手で確認する。")
                return 1
        finally:
            shutil.rmtree(vdir, ignore_errors=True)

        print("\n完了。全ファイルのハッシュ一致を確認した。")
        if bumped:
            print(f"※ SCORING_AUDIT.md に {bumped[1]} として追記すること。")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
