# カジ競馬 X自動投稿（Cloudflare Worker）

PC不要・窓なしで毎日Xに自動投稿する。画像・文章は本番の `tweet.html` を
Browser Rendering で開いて生成する（`?auto=morning|evening`）。

- 朝 8:00(JST)：各場の予想カード（4枚/ツイート分割・「M/D ◯◯競馬の予想です」）
- 夜 21:30(JST)：①的中まとめ ②回収率です＋画像2 ③段階別成績 ④答え合わせ

## 仕組み
`src/worker.js` … cron(23:00/12:30 UTC)で起動 → ヘッドレスChromeで tweet.html を開く
→ `window.__autoOut` を読む → X API(OAuth1.0a)でスレッド投稿。
`DRYRUN=1` の間は**投稿しない**（内容確認のみ）。

## デプロイ手順（あなたの操作が要る所）

### 0. 有効化（Cloudflareダッシュボード・1回だけ）
1. **Workers を有料プラン($5/月)** にする（Browser Rendering に必要）
2. **Browser Rendering を有効化**（ダッシュボードで案内が出る）

### 1. 認証とデプロイ（このフォルダで）
```
cd tools/x-autopost
npm install
npx wrangler login            # ブラウザが開く→許可（あなたの操作）
npx wrangler deploy
```

### 2. Xの鍵を secret に登録（値は画面に出ない・安全）
```
npx wrangler secret put X_API_KEY
npx wrangler secret put X_API_SECRET
npx wrangler secret put X_ACCESS_TOKEN
npx wrangler secret put X_ACCESS_SECRET
npx wrangler secret put TRIGGER_KEY      # 手動テスト用の合言葉（好きな文字列）
```

### 3. ドライランで中身を確認（投稿しない）
デプロイ後のURL（例 `https://kajikeiba-autopost.<あなた>.workers.dev`）に:
```
/run?kind=morning&dry=1&key=<TRIGGER_KEY>
/run?kind=evening&dry=1&key=<TRIGGER_KEY>&mode=nar
```
→ 各ツイートの text と画像枚数がJSONで返る。Browser Rendering が
   tweet.html を捌けるかもここで分かる。

### 4. 本番投稿をオンにする
`wrangler.toml` の `DRYRUN = "1"` を `"0"` にして `npx wrangler deploy`。
以降 cron(朝8:00 / 夜21:30 JST)で自動投稿。まず `/run?...&dry=` を付けずに
1回手動実行して、実際に投稿されるのを見てから任せるのが安全。

## 注意 / 既知の論点
- **画像投稿はXの有料プラン(Basic)が要る場合がある**。無料で弾かれたらBasicへ。
- Browser Rendering の実行時間: 夜の全場照合で最大~90秒。上限は `RENDER_TIMEOUT_MS`。
- 予想はオッズ前・公開後不変。狙い目は朝の保存信頼度基準（tweet.html側で担保済み）。
- tweet.html は legacy 配信。`?auto=` はゲート自動通過（公開予想の生成のみ）。
