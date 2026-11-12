# CLAUDE.md — Claude Code 作業指針

このファイルは Claude Code が自動で読み込む。SW TURF LAB（地方競馬AI予想PWA）の開発を引き継ぐ。

## どのドキュメントを見るか

| やること | 見るファイル |
|---|---|
| **今なにが事実として確定しているか**（因子の効果・却下済み・回収率の現実） | **docs/FACTS.md** |
| **因子や買い方を検証する**（手順・分母の取り方・サンプル数の目安） | **docs/BACKTEST_PROTOCOL.md** |
| **予想人格が本物か**（実測値・削除した人格と理由・偽物の見抜き方） | **docs/PERSONAS_AUDIT.md** |
| **データの列定義・rid形式・落とし穴** | **docs/DATA_SOURCES.md** |
| **公開サイトの構造・画面・これから作るもの** | **docs/SITE_MAP.md** |
| **事業設計（何を売るか・集客・収益・法務）** | **docs/BUSINESS.md** |
| UI・画像を作る/直す | docs/DADS_DESIGN.md |
| 経緯を知りたい・上記で答えが出ない | docs/SCORING_AUDIT.md（時系列の全作業ログ） |

FACTS/PROTOCOL/DATA_SOURCES は AUDIT から「引くための情報」を抜き出したもの。
**矛盾したら AUDIT が原本**。新しく確定した事実は両方に反映する。

以下は要点。

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

**データはサーバーにも退避してある**（2026-07-30・ユーザー指示「基本的にデータは全て
サーバーに残してね」）。`/seventh-well.com/backup/` にローカルと同じ構成で置き、
`.htaccess` で全拒否（403確認済み）。`python backtest/backup_data.py --push` で更新。
tier1=keiba.go.jp月次ZIP+Open-Meteo降水量（183MB・**源が死ぬと再取得不能**）/
tier2=学習済みモデルと索引サイドカー（15MB）を保存済み。
tier3=派生jsonl（1.8GB）とtier4=jvdata（3.3GB）は未送（`--tier 3`で送れる）。

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
**この項目を「証明された黒字」として扱わないこと。対外公表も止めること。**
（詳細は docs/FACTS.md の同項目。以下は要点）

- **156%は「後知恵の⭐」で出していた公算が大きい。**
  ⭐の定義「最終角位置÷頭数≤0.35」を**そのレース自身の**通過順で判定すると
  ROI240%(697R)。だが最終角位置は**発走前には分からない＝賭けられない**。
- **実際に賭けられる予測版（kochi.htmlが使うstyle⭐）は ROI 43%(154R)＝負け。**
- 2026-07-30の独立再検証でも再現せず: その日の最終競走で⭐フォメを組むと
  近走平均先行度 56.6%(77R) / 前走 29.5%(239R) / 近走ベスト 48.5%(771R)。
  ★3セッション+今回の計4回、誰がやっても156%は再現できていない★
- ⭐≧2で「⭐1着固定3連単フォメ（1着⭐/2着上位5/3着上位7）」という買い方自体は
  kochi.htmlで稼働中。ただし上記のとおり期待値の裏付けは無い。
- **平場（通常戦）は回収率で稼げない**（◎複勝80%止まり・3連単どの型も控除率負け）。平場の価値は「精度＝当たってる感」で見せるもの。

### kochi.html（高知ファイナル専用・独立ページ）
- 通常予想フローに依存せず、開いたら自動で今日の高知ファイナルを取得→⭐フォメ表示。
- tweet.htmlから必要関数を依存再帰で抽出して自己完結。
- proxy.phpは絶対パス `/odds/proxy.php` で叩く（v356で相対→絶対に修正済み）。

---

## 未着手・次の課題

**残っているのはユーザー判断・外部入力待ちのものだけ**（2026-08-04時点。SITE_MAP §7も参照）:
- 1日だけ見られる有料ページ（パスワード）／自動ツイート（X APIキー待ち）／tweet.htmlの保護
- 中央編のコンテンツ（JV-Link 11年分が入ってから）

### 済（2026-08-03〜04にまとめて消化）
- lab.htmlの展開アニメ同期 → v4.3.38でコース楕円版に統一
- 週間成績の自動画像 → `backtest/gen_weekly_image.js`（毎週月曜・daily.py）
- オッズ7分前vs2分前検証 → `backtest/odds_drift.py` 実測（1人気は7分前→締切で中央値-10.5%）
- オッズ画面(P1) → race.htmlのオッズボード（複勝/馬連/ワイド/馬単・v4.3.40）
- 見送りレース編の記事(P2) → `/data/miokuri/`（触れ込みの「配当が桁違い」は実測で否定）
- 人格の週次成績(P2) → /ai/通信簿の「今週」列
- 資金曲線の高精細画像 → puppeteer+HTMLの基盤は gen_weekly_image.js に用意済み（流用可）
- ⭐フォメの3着頭数 → ⭐定義の再現ゲートを通らないため保留（docs/FACTS.md 高知の項）

### 恒常的に効いている見張り（壊れたら気づけるように）
`npm run check` と daily.py に以下を入れてある。**新しい仕組みを足したらここにも足す**:
- `check_claims.py` 公開数字の台帳照合＋**表示に出る未登録の数字**を検出（自己診断つき）
- `check_netkeiba_layout.py` netkeibaのHTML構造変更（取得が静かに空になる壊れ方）
- `check_stale.py` 入力より古い生成物（pmarks.json＝確定印も対象）
- `bt_persona_marks.js` は出力が空・半減なら**書かずにexit 1**（確定印が静かに消えない）

## データを更新したときのチェックリスト

**データを増やしたら、それを読んでいる生成物を全部たどって作り直す。**
これを2回怠って本番に嘘が出た（中央1年分と地方13年分を「同じ式で比較」と書いた／
削除した人格が紹介ページに残っていた）。

```
python backtest/check_stale.py        # 入力より古い生成物を一覧
python backtest/check_stale.py --fix  # 古いものだけ作り直す
python backtest/check_data_health.py  # 入力データ自体の重複/欠損（別名同一ファイル・NAR欠け月）
python backtest/deploy.py --site public --push
# ★PHPを直したら --php を必ず付ける★ 付け忘れるとPHPだけ古いまま残り、
#   「JSは新項目を送るのにサーバーが白リストで捨てる」という気づきにくい壊れ方になる
python backtest/deploy.py --site legacy --php --push
```
※check_data_health.pyは2026-07-26追加。race_2024.txt/race_2025.txtが
JV-Linkバグで同一ファイルになっていた事故（詳細はSCORING_AUDIT.md）を機械で拾う。
npm run check にも組込済み。

## 開発時のチェックリスト（tweet.html変更時）
1. JS構文チェック: `node -e "new Function(require('fs').readFileSync('script.js','utf8'))"`
   （script.jsは `python3 -c "import re;open('script.js','w').write(re.findall(r'<script>([\s\S]*?)</script>',open('tweet.html').read())[0])"` で抽出）
2. sw.jsのキャッシュトークン odds-anomaly-vNNN を +1
3. バックテストで複勝率/ROIが落ちてないか確認（落ちたら戻す）
4. UI/画像なら DADS準拠（コントラスト・フォント段階）を機械チェック
5. SCORING_AUDIT.md に追記
6. **モデルに列を足したら `node backtest/check_model_wiring.js`**（npm run check に同梱）。
   列を1本足すと触る場所は5箇所ある：供給2経路（tweet.html の ltrFeatTweet /
   core/personas.js の ltrFeat）・索引の生成（build_jockey_index.py）・
   デプロイ設定2つ（MAP と PUBLIC_MAP）・日次(daily.py)。
   **人間の記憶で辿ると必ず漏れる**（2026-07-30に第2弾の5列が personas.js に
   渡っていないのを、このチェックを作って初めて発見した。どれもエラーが出ず
   精度だけ静かに落ちる）。
7. **採点ロジック（fundamentalScore/gbmScore/speedIndex等）を触ったら
   `python backtest/check_scoring_sync.py` を回す。** tweet.htmlはcore/scoring.jsを
   読み込まず同じ関数群を自前でコピーして持っている（統合はリスクが大きいため見送り済み・
   docs/SCORING_AUDIT.md参照）。片方だけ直すと二重管理がズレて片方だけ古いスコアで動く。
8. **`npm run check`** で1〜7のうち機械化できる分（構文チェック・採点同期・
   生成物の鮮度・テーマ変数）をまとめて回せる。デプロイ前チェックの最低ライン。
   `deploy.py --push`はこの一部（構文チェック・採点同期）を自動実行するが、
   全部は回さないので、大きめの変更の後は手動で`npm run check`も叩くこと。
