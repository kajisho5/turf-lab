# SW TURF LAB — 開発引き継ぎパッケージ

地方競馬AI予想PWA。本番: https://seventh-well.com/odds/
このパッケージは Claude Code で開発を継続するための一式。**まず `docs/SCORING_AUDIT.md` を全部読むこと**（全作業履歴・検証結果・触るな領域が書いてある）。

---

## 最重要の鉄則（盛らない・データ主義）

1. **スコア/UI変更は必ずバックテストで前後比較 → 複勝率/ROIが落ちたら理論的に正しくても戻す。**
2. **ROI集計は必ず「買った全レースを分母に」。** 的中時だけ投資計上する実装は回収率を偽装する（過去に「複勝黒字」と誤結論した重大バグあり。詳細はAUDIT）。
3. **GBMモデルは触らない**（再学習・生値修正禁止。GBM出力への後付け加算はOK）。
4. **UI/画像を作る/直す時は必ず `docs/DADS_DESIGN.md` を参照**：コントラスト4.5:1以上・本文16px以上・フォントはDADS段階のみ。色はコントラスト計算で検証。
5. バグ修正は全return・全経路を確認し、実際に実行して出力を見てから「直った」と言う。
6. 不具合調査は端末キャッシュのせいにする前に curl（キャッシュバスター付き）でサーバーの実物を確認。

---

## ディレクトリ構成

```
deploy/      本番デプロイファイル（手動でサーバーに上書きアップ）
  tweet.html    メインアプリ（~560KB・予想取得/答え合わせ/各種画像生成）
  kochi.html    高知ファイナル専用の独立ページ（新規・下記参照）
  sw.js         Service Worker（キャッシュトークン odds-anomaly-vNNN を変更のたび+1）
  lab.html      lab（成績ダッシュボード・未同期の機能あり）
  index.html, scoring_explainer.html, kaiko.html, lab-* : 補助
php/         サーバーサイド（seventh-well.com/odds/ 上で動く）
  proxy.php       netkeiba取得プロキシ（?u=base64url で叩く。WAF対策でurl=は使わない）
  predictions.php 予想の保存/読み出し（lab用）
  nardata.php     馬別近走履歴API・keiba.go.jp当日ZIP取得
  cleanup.php     サーバー容量掃除
  他: results/horse/jockey/bias/oddslog/unzip
docs/
  SCORING_AUDIT.md  ★全作業記録（これを最初に読む）
  DADS_DESIGN.md    デジタル庁デザインシステム（UI基準）
backtest/
  backtest.py         実測先行力等の検証スクリプト
  nar_data_pipeline.py keiba.go.jp公式データのDL〜JSON変換
  bt_realmodel/       実モデル大規模BTハーネス（h3.js=ps注入 / bt3.js=ランナー / bt3all.sh）
data/
  jusho_profiles.json  重賞557レース×直近10開催の傾向
  gbm_model_backup.json GBMモデルのバックアップ（触らない）
samples/     画像サンプル（資金曲線の完成形など）
```

**注意: 大容量データ（バックテスト本体）は別。** 必要なら再生成する:
- `pays_fullhistory.json`（16MB・全期間複勝払戻）
- `bt_dataset.json`（42MB・直近5年68,280R）
- `nar_payback/`（139本のpayback.csv・全券種確定払戻2015-2026）
- `bt_realmodel`用のJSONL（27,315R・約475MB・揮発）
これらは `backtest/nar_data_pipeline.py` で keiba.go.jp から再取得できる。

---

## データ源（keiba.go.jp 公式・最重要）

netkeibaスクレイピングの代替。直リンクでZIP取得可（UTF-8・CSV・全13場）:
```
レース: https://www.keiba.go.jp/KeibaWeb/DataDownload/RaceDataDownload?type=monthly&k_year=YYYY&k_month=M
オッズ: https://www.keiba.go.jp/KeibaWeb/DataDownload/OddsDataDownload?type=monthly&k_year=YYYY&k_month=M
```
- RaceDataDownloadのZIPに **payback.csv が同梱**（単複/ワイド/馬連馬単/3連複/3連単の確定払戻・28年分1998-）。
- レース情報1998年〜 / オッズ2026年3月〜 / 払戻は全期間。
- `python3 backtest/nar_data_pipeline.py 202401 202607` でDL〜変換。

## rid（レースID）形式
**rid = YYYY(4) + TC(2) + MMDD(4) + RR(2)**。例 `202654071812` = 2026年・高知(54)・07/18・12R。
TC: 帯広11/門別30/盛岡35/水沢36/浦和42/船橋43/大井44/川崎45/金沢46/笠松47/名古屋48/園田50/姫路51/高知54/佐賀55。
payback.csvのキー = (場名, YYYYMMDD, R番号ゼロ埋め無し)。

## netkeiba取得の注意
- 出馬表/結果/一覧は**全てUTF-8**（過去にEUC-JPと誤認し文字化けでファイナル判定失敗した教訓）。charset宣言を見れば正しく読める。
- 取得経路: `/odds/proxy.php?u=` + base64url(URL)。**絶対パスで叩く**（相対だとルート表示のブラウザで404になる）。

---

## 現在の到達点（2026-07-18時点）

### 予想スコアリング（tweet.html）
- 最終スコア=GBM（決定木）。線形fundamentalScoreはフォールバック兼スケール基準。
- 採用済み新因子: **実測先行力**（v304・近走コーナー通過順÷頭数）、**レースレベル**（v324・標準タイム−勝ちタイム）。両方GBM出力へ後付け加算。
- ベースライン複勝率: 実モデル大規模26,731Rで61.7%（公式入力）/ netkeiba入力946Rで63.3% / 複ROI 80-87%。

### 【要検証】高知ファイナル⭐フォメ — ★ROI156%は再現できていない★
**「証明された黒字」として扱わないこと。対外公表も止めること。**（詳細 docs/FACTS.md）
- **156%は後知恵の⭐で出していた公算が大きい。** ⭐の判定「最終角位置÷頭数≤0.35」を
  **そのレース自身の**通過順で行うとROI240%(697R)＝AUDITの638Rにほぼ一致するが、
  **最終角位置は発走前に分からない＝賭けられない**。
- **実際に賭けられる予測版（kochi.htmlが使うstyle⭐）は ROI 43%(154R)＝負け。**
- 2026-07-30の独立再検証でも再現せず（近走平均56.6% / 前走29.5% / 近走ベスト48.5%）。
  ★計4回、誰がやっても156%は再現できていない★
- 買い方自体（⭐≧2で⭐1着固定3連単フォメ）はkochi.htmlで稼働中。期待値の裏付けは無い。
- **平場（通常戦）は回収率で稼げない**（◎複勝80%止まり・3連単どの型も控除率負け）。平場の価値は「精度＝当たってる感」で見せるもの。

### kochi.html（高知ファイナル専用・独立ページ）
- 通常予想フローに依存せず、開いたら自動で今日の高知ファイナルを取得→⭐フォメ表示。
- tweet.htmlから必要関数を依存再帰で抽出して自己完結。
- proxy.phpは絶対パス `/odds/proxy.php` で叩く（v356で相対→絶対に修正済み）。

---

## 未着手・次の課題
- **⭐が1・2着に来た時、3着を何頭まで広げれば期待値最大か**（7/18は8→6→12で1・2着的中も3着12番=11人気を外した。3連単96,560円を逃した）。⭐1着固定3着全流しのROIをpaybackで再検証する価値あり。
- 資金曲線などの高精細画像は puppeteer+HTML/SVG で生成（canvas手描きより綺麗）。Claude Codeなら生成の自動化もしやすい。
- lab.htmlの展開アニメ同期、週間成績の自動画像、オッズ7分前vs2分前検証（要スナップショット記録の仕込み）。

## 開発時のチェックリスト（tweet.html変更時）
1. JS構文チェック: `node -e "new Function(require('fs').readFileSync('script.js','utf8'))"`
   （script.jsは `python3 -c "import re;open('script.js','w').write(re.findall(r'<script>([\s\S]*?)</script>',open('tweet.html').read())[0])"` で抽出）
2. sw.jsのキャッシュトークン odds-anomaly-vNNN を +1
3. バックテストで複勝率/ROIが落ちてないか確認（落ちたら戻す）
4. UI/画像なら DADS準拠（コントラスト・フォント段階）を機械チェック
5. SCORING_AUDIT.md に追記

---

## GitHub からの公開（2026-11-13〜）

このリポの main に反映すると、GitHub Actions が Cloudflare に公開する（パソコン不要）。
Cloudflare の鍵は [tower](https://github.com/kajisho5/tower) が自動で作ってこのリポの Secrets に入れる（`projects/turf-lab.toml`）。

| ワークフロー | 動くとき | 公開先 |
|---|---|---|
| deploy-site | deploy/・core/・cloudflare/ などが変わったとき、手動 | Worker「kajikeiba-turf」（seventh-well.com/odds・/lab） |
| deploy-autopost | tools/x-autopost/ が変わったとき、手動 | Worker「kajikeiba-autopost」（X自動投稿） |

- 2026-11-13 の取り込み時点で、配信物677ファイルと Worker のプログラムが本番と一致することを確認済み。
- パソコン側の `Desktop\odds` から反映すると、ここと食い違う。**今後の反映はこのリポからだけ行う**（パソコン側は、次につないだ時にこのリポの写しに置き換える）。
- 大きな検証データ・学習の道具（backtest/bt_realmodel など）はまだパソコンにしかない。
