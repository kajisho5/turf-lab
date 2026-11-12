# Cloudflare移行 設計書（PHP全廃）

作成 2026-10-29。**現物と食い違ったら現物が正しい。**

## 1. 目的

お名前.com（PHP）で動いている競馬の3サイトを、Cloudflareだけで動くように作り直す。

| # | サイト | 今 | 移行後 |
|---|---|---|---|
| 1 | 公開サイト kajikeiba.com | お名前.com（PHP 10本＋.htaccess） | Cloudflare Worker |
| 2 | 運営用 seventh-well.com/odds/ | お名前.com（PHP 15本＋cron） | 同じWorker |
| 3 | 知人向け seventh-well.com/lab/ | お名前.com（公開サイトの書き換えコピー） | 同じWorker |

**最重要の約束: URLとHTML/JSは1文字も変えない。**
`tweet.html` も `race.html` も今のまま。`/odds/predictions.php` のような
PHPのURLも、Worker が同じURL・同じ応答で受ける。
だから画面側の改修はゼロで、PC側の自動処理（daily.py が叩くHTTP）もそのまま動く。

## 2. 技術選定

| 候補 | 動作の軽さ | 配布サイズ | 作りやすさ | 対応 | 将来性 | AIでの書きやすさ |
|---|---|---|---|---|---|---|
| **A. Workers＋静的配信＋D1（推奨）** | ◎ 世界中の拠点で実行 | 静的は無料・無制限 | ◎ 1つのWorkerで3サイト | ブラウザ全部 | ◎ Cloudflareの主力 | ◎ |
| B. Pages＋Functions＋D1 | ◎ | 同じ | ○ | 同じ | △ 公式が「新規はWorkersで」と明言 | ○ |
| C. Workers＋R2（データをファイルで保存） | ○ | 同じ | △ 一覧・集計が遅い | 同じ | ○ | ○ |

**A を採用。** 根拠: 公式が新規はWorkersを推奨（Pagesは保守のみ）
https://developers.cloudflare.com/workers/best-practices/workers-best-practices/
Astro は使わない。中身は「表示中心のサイト」ではなく、JSで全部動くアプリ（tweet.html 944KB 等）なので利点が無い。
Hono（ルーター）も使わない。URLがPHPのファイル名そのもの（/odds/predictions.php 等）で、振り分けは表1枚（src/index.ts）で済むため。

### 使う版（2026-10-29 に npm 公式で確認）

| もの | 版 | 根拠 |
|---|---|---|
| wrangler（デプロイ道具） | 4.155.0 | https://www.npmjs.com/package/wrangler |
| fflate（公式ZIPの展開） | 0.8.3 | https://www.npmjs.com/package/fflate |
| TypeScript | 7.0.2 | https://www.npmjs.com/package/typescript |
| @cloudflare/workers-types | 5.20261029.1 | https://www.npmjs.com/package/@cloudflare/workers-types |

## 3. 構成

```
              ┌────────────── Cloudflare ───────────────┐
kajikeiba.com ─┤ カスタムドメイン                          │
seventh-well.com/odds*  ─┤ ルート（※1）                   │
seventh-well.com/lab*   ─┤ ルート（※1）                   │
              │   Worker "kajikeiba-turf"                 │
              │    ├ 静的配信  dist/k  dist/s/odds  dist/s/lab
              │    ├ PHP相当API（同じURL）                 │
              │    ├ cron（odds-cron・sitemap収集・掃除）  │
              │    └ D1 "kajikeiba"（予想・回顧・結果…）   │
              └──────────────────────────────────────────┘
```
※1 ルートはカスタムドメインより優先される（公式: https://developers.cloudflare.com/workers/configuration/routing/routes/ ）。
会社HP用の `seventhwell-site` がいつ seventh-well.com 全体を受け持っても、
/odds と /lab だけはこのWorkerに来る。お互いに干渉しない。

### ホストとパスの振り分け

| 来たURL | 中身 |
|---|---|
| kajikeiba.com/〜 | dist/k/〜（公開サイト） |
| kajikeiba.com/odds/〜, /lab/〜 | 404（運営用を公開側に漏らさない） |
| seventh-well.com/odds/〜 | dist/s/odds/〜 |
| seventh-well.com/lab/〜 | dist/s/lab/〜（ブランド・パスを書き換えた版） |
| *.workers.dev（検証用） | /odds・/lab はそのまま、それ以外は公開サイト |

### .htaccess の置き換え

| .htaccess の機能 | Worker での実装 |
|---|---|
| http→https | Worker 側で301 |
| AIクローラー・curl等のUAを403 | 同じ正規表現で403（公開・lab） |
| 索引ファイルの直リンク禁止 | 同じ条件（Referer）で403 |
| /race/{12桁}/ → race.php | SSR（サーバー側でHTML生成）を同じ文面で |
| sitemap.xml → sitemap.php | 同じ |
| /cache/ を404 | 同じ |
| lab の noindex | X-Robots-Tag を付与 |

## 4. PHP → Worker 対応表（全22本）

| PHP | 使う所 | 保存先 | 備考 |
|---|---|---|---|
| proxy.php | 全ページ | D1 proxy_cache | 直取得→jina中継→古いキャッシュの3段構えを維持。90秒の連打防止・6時間のフォールバックも同じ |
| proxy_seed.php | PC(seed_*.js) | D1 proxy_cache | トークンも同じ |
| predictions.php | tweet/lab/kochi/PC | D1 predictions, locks | noclobber・savedAt・並び順も同じ。全件一覧は分割して流す |
| kaiko.php | tweet/kaiko/lab | D1 kaiko | ※ソースがリポに無い。応答から仕様を復元（put＝key単位で上書き、list＝全件） |
| results.php | tweet/lab/PC | D1 results | 120日間引きは「全部残す方針」に合わせて止める（下記7） |
| horse.php / jockey.php | tweet | D1 horses / jockeys | |
| bias.php | tweet | D1 bias | |
| oddslog.php | tweet/kochi/PC | D1 odds_snaps | 同一分の上書き・post/mtp の白リストも同じ |
| odds-log.php（旧） | anomaly.html | D1 oddslog_old | 使っていない旧ページ用。読み書きとboardは移植 |
| cleanup.php | tweet | D1 | 使用量レポートはD1の実容量で出す |
| nardata.php | （cron） | D1 | daily/collect/get/batch/info |
| line_push.php | tweet（LINE運転） | D1 line_outbox/line_sent ＋ 秘密の鍵 | 二重送信防止の印も移行する |
| error_log.php / errlog_view.php | tweet・公開 | D1 js_errors | サイト別 |
| stats.php / stats_view.php | 公開・lab | D1 pv | Cookieなし・IP非保存の方針そのまま |
| race.php | 公開・lab | D1 ssr_cache | 発走前3分・確定後1日のキャッシュも同じ |
| sitemap.php (+sitemap_urls.php) | 公開 | D1 race_index | 毎回60リクエスト投げる方式をやめ、cronで日ごとに貯める |
| nar_official.php | 公開 | D1 ssr_cache | |
| unzip.php / unzip_horse.php | 不要 | — | 「Cloudflareでは不要」と返すだけ |
| odds-cron.php（お名前のcron） | anomaly.html | D1 | Workerのcron（9-23時・5分おき）で同じ処理 |

## 5. データベース（D1）

テーブルは `cloudflare/migrations/0001_init.sql`。1つのDBに全部入れる。
本文はPHP時代のJSONファイルの中身を**そのまま文字列で保存**する（形を変えない＝読み出した物が今と同一）。

量（2026-10-29 実測）: 予想 568件 57.7MB / 結果 4,656件 7MB / 馬 11,447件 11.6MB /
オッズ時系列 2,911件 1.5MB / 回顧 689件 5.8MB。予想は年に約200〜450MB増える。

## 6. 料金と制限（重要）

| | 無料 | 有料（Workers Paid 月$5） |
|---|---|---|
| 1回のCPU時間 | **10ミリ秒** | 30秒（最大5分） |
| D1 1つの大きさ | **500MB** | 10GB |
| 1回で投げられる外部リクエスト | 50 | 10,000 |
| 1日のリクエスト | 10万 | 無制限（月1,000万まで込み） |

出典: https://developers.cloudflare.com/workers/platform/limits/ ・ https://developers.cloudflare.com/d1/platform/limits/

**有料プランを推奨。** 無料だと、予想の全件一覧（旧lab.html）や公式ZIPの展開が10ミリ秒を超えて止まりうる。
また予想は1年弱でD1の500MBに届く。

## 7. 方針の変更点（挙動が今と違う所は全部ここに書く）

1. results.php の「120日より古い結果を消す」は**やめる**（cleanup.php の「全部残す」方針と矛盾していたため）。
2. sitemap.php は毎回netkeibaに60回取りに行く方式から、**cronで毎日レースIDを貯めて**出す方式に変える（出力の形は同じ）。
   切替直後は貯まっている日数が少ない。毎晩14日ずつ埋まるので、2晩で30日そろう。
3. race.php: 確定済みの結果ページは1日キャッシュする（PHP版はコメントの意図に反して3分ごとに取り直していた）。
4. odds-cron: 1回の外部取得を45本までに抑える（無料プランの上限50本）。収集中データは36時間で捨てる
   （PHP版は結果照合できなかったレースが残り続け、5月のレースが今も「串刺しボード」に出ていた）。
5. 保存した記録の空の `{}` は `{}` のまま残る（PHPは `[]` に変えて保存していた）。画面側はどちらでも動く。
6. unzip系は不要なので「不要です」と返す。/odds/odds-cron.php をブラウザで開くと最後の実行結果を返す。
7. netkeibaの取得が直接できない時、race.php・sitemap用の取得も proxy.php と同じ中継（r.jina.ai）を試す。

### 調べて分かった事実（移行と関係なく）
- 旧サーバーの odds-cron は**6/7を最後に記録が止まっている**（odds-log の最新が jra 6/7・nar 6/6）。cron 自体が止まったか、
  取得が失敗し続けているかは、サーバーのcronログを見ないと分からない（未確認）。新しい Worker の cron はローカル試験で動いた。

### netkeiba は Cloudflare から取れるか（2026-10-29 実測で確認済み）
proxy.php のコメントに「Cloudflare Worker のIP帯は netkeiba に弾かれる」とあったので、既存の Worker
`netkeiba-proxy`（6月に作ったもの）経由で実際に取った: 地方の一覧・中央の一覧・出馬表・db.netkeiba の馬ページ・
オッズAPI、**全部 200**。今は弾かれていない。ただし相手次第で変わるので、弾かれたら jina 中継に落ちる作りは残す。

## 8. 移行手順

1. Cloudflareに D1 を作り、テーブルを作る
2. Worker を workers.dev（検証用URL）に出す
3. `cloudflare/migrate.py` で旧サーバーの全データをD1に写す（何度流しても同じ結果。差分だけ更新）
4. 新旧を同じ入力で叩いて応答を突き合わせる
5. **切替（ここで止まって確認）**
   - seventh-well.com: DNSの「プロキシ（オレンジ雲）」をON → ルート `seventh-well.com/odds*` `seventh-well.com/lab*` を有効化
   - kajikeiba.com: Cloudflareにサイトを追加 → お名前.comでネームサーバーを変更 → Workerにドメインを付ける
6. 切替直前にもう一度 migrate.py を流して最新分を写す
7. 戻し方: ルートを外す／ネームサーバーを戻すだけで旧サーバーに戻る（旧サーバーは1か月は消さない）

## 9. PC側の自動処理への影響

| スクリプト | 影響 |
|---|---|
| daily.py の各HTTP取得（push_results, haisha_shadow, placebo, gen_weekly_image…） | **無改修**（URLが同じ） |
| deploy.py（WinSCP/FTP） | `cloudflare/deploy_cf.py` に置き換え。daily.py の最後の「公開サイトへ反映」もこちらへ |
| sync_pred_data.py（WinSCPで同期） | HTTPで取る版に置き換え |
| backup_data.py（FTPでサーバーへ退避） | R2 へ退避する版が必要（今回は未対応・後述） |
| LINE runner | **無改修**（URLが同じ） |
