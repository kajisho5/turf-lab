# cloudflare/ — PHP をやめて Cloudflare だけで動かす一式

設計と理由は `docs/CLOUDFLARE_MIGRATION.md`。ここは「何がどこにあるか」と「手順」だけ。

## 中身

| もの | 役目 |
|---|---|
| `wrangler.jsonc` | Worker の設定（静的配信・D1・cron・切替時のルート） |
| `src/index.ts` | 入口。ホストとパスで3サイトに振り分け、`.htaccess` 相当（ボット拒否・直リンク拒否・https・/race/ID/）もここ |
| `src/api/*.ts` | PHP 1本ずつの置き換え。URL・応答の形は PHP と同じ |
| `src/cron.ts` | お名前.com の cron（odds-cron.php）の置き換えと、sitemap 用のレースID収集 |
| `src/admin.ts` | 移行・バックアップ用の管理口（合言葉つき） |
| `src/gen/meta.ts` | **自動生成**（build.py）。race.php の `?v=` ハッシュ・重賞名・sitemap の静的URL・lab の書き換え規則 |
| `migrations/0001_init.sql` | D1 の表 |
| `build.py` | `dist/` を作る。置き場所の一覧は `backtest/deploy.py` のものをそのまま使う（ここには持たない） |
| `deploy_cf.py` | 本番反映（deploy.py の置き換え。差分→安全ゲート→sw.js +1→確認→反映→照合） |
| `migrate.py` | 旧サーバーのデータを D1 へ写す（ftp-pull / http-pull → push → verify） |
| `sync_pred_cf.py` | 予想をローカルへ同期（sync_pred_data.py の切替後の取得元） |
| `scripts/selftest.py` | ローカルの Worker が PHP と同じ応答をするかの試験（架空データのみ） |
| `static_extra/` | サーバーにだけ置いてあった静的ファイル（2026-10-29 に本番から取得） |
| `deploy_cf.json` | 切替スイッチ（`use_cloudflare`）と確認用URL |

## 手元で動かす

```
cd cloudflare
npm install
python build.py --site both
npx wrangler d1 migrations apply kajikeiba --local
npx wrangler dev            # http://127.0.0.1:8787/ が公開サイト、/odds/ /lab/ が運営・lab
python scripts/selftest.py  # 別の窓で
```

## 初回の準備（1回だけ）

```
set CLOUDFLARE_API_TOKEN=（Cloudflareのトークン）
python cloudflare/deploy_cf.py --setup
```
D1 の作成・表の作成・workers.dev への配置・管理口の合言葉（`cloudflare/.admin_token`）の登録までやる。

## 毎回の反映

```
python cloudflare/deploy_cf.py --site public --push     # 公開サイト
python cloudflare/deploy_cf.py --site legacy --push     # 運営用 /odds/（sw.js のトークンも自動で+1）
python cloudflare/deploy_cf.py --site lab --push
```
`cloudflare/deploy_cf.json` の `use_cloudflare` を `true` にすると、daily.py の最後の反映と
sync_pred_data.py の取得元が Cloudflare に切り替わる（それまでは今まで通り FTP）。
