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


## 手で出し直しを頼む（Muse などから・2026-11-22）
自動の夜の回が失敗して、やり直しでも出なかった時に、URL を開くだけで頼める。
```
# 1) 状態を見る（何も起きない）
https://<ワーカーのURL>/redo?kind=evening&mode=jra&key=<TRIGGER_KEY>
# 2) 頼む（go=1 が付いた時だけ動く）。mode は nar（地方）か jra（中央）、date は省略で今日（昨日まで可）
https://<ワーカーのURL>/redo?kind=evening&mode=jra&key=<TRIGGER_KEY>&go=1
```
- 頼むと次の10分ごとの回で **1回だけ** 出し、結果をメールで知らせる。
- すでに投稿できている回・待っている依頼がある時・2日以上前は断る。依頼のあとに自動のやり直しが先に成功していたら、実行時にも出さない（二重投稿よけ）。
- 朝の回は対象外（今は夜だけ）。TRIGGER_KEY は Cloudflare の Variables and Secrets にある（値はここに書かない）。


## 段階に分けた動き（2026-11-23〜）
朝・夜の回は「取得 → 確認 → 生成 → 確認 → 投稿」の順に進む。欠けがあればそこで止まり、理由を残してメールで知らせる。
いつもの日は今までどおり最後まで自動で進む（止まるのは欠けがある時だけ）。

| 段階 | すること | 次に進む条件 |
|---|---|---|
| 取得 fetch | 朝＝予想を作って保存／夜＝結果を取って保存（画像は作らない） | 保存できた件数が対象のレース数とそろう（見送り・取消は欠けに数えない）。中央の朝は、朝の前に一覧から拾ったレースも対象に入れる |
| 生成 gen | 朝＝**保存した予想から**画像と文を作る（作り直さない）／夜＝答え合わせの画像と文 | 場の数ぶんの画像・投稿の文がある。画像と文はデータベース（xpost_gen 表、4日で消える）に保存 |
| 投稿 post | 保存した画像と文を X に出す | 投稿済み・途中まで投稿済みなら二度と出さない |

- 中央の予想は **7:00・7:20・7:40・8:00 に先に取得**する（その日の一覧が取れている日だけ。8:00 でも欠けていたらメール）。8:30 の回は取得し直さず、保存から画像を作って出す。止める時は変数 `EARLY_JRA="0"`
- 投稿で X が断った時のやり直しは、保存した画像でそのまま出す（ページを開き直さない）
- 段階の状態は xpost_log の `st:<日付>:<morning|evening>:<nar|jra>` に残る

### 状態を見る・段階を手で動かす（Muse からも可）
```
# その日の状態を見る（何も動かさない）
https://kajikeiba-autopost.kajisho5.workers.dev/stage?key=<TRIGGER_KEY>[&date=YYYYMMDD]
# 段階を動かす（次の10分ごとの回で1回）。step は fetch・gen・post・all（all＝足りない段階から最後まで）
https://kajikeiba-autopost.kajisho5.workers.dev/stage?key=<TRIGGER_KEY>&kind=morning&mode=jra&step=fetch&go=1
# 取得・生成を済みでもやり直す時は &force=1（投稿済みは force でも出し直さない）
# 取得が欠けたまま、承知のうえで生成・投稿へ進める時は &accept=1（例: 取消扱いにならないレースが1つだけ残った夜）
```
予想の件数は予想ページの側でも見られる: `https://seventh-well.com/odds/predictions.php?action=summary&date=YYYYMMDD&mode=jra`
