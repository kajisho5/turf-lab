# カジ競馬 自動投稿の段階操作（Muse 用）

X（@kaji_keiba）への自動投稿は、次の順に進む。

**取得 → 確認 → 生成 → 確認 → 投稿**

いつもの日は全部自動で進む。止まるのは欠けがあった時だけで、その時は理由がメールで届く。
このメモのURLを開くと、状態を見たり、各工程を手で動かしたりできる。

## 使う前に
- `<KEY>` は合言葉（TRIGGER_KEY）に置き換える。値はこのメモには書かない。
- `go=1` が付いたURLは、**次の10分ごとの回で1回だけ**動く。結果は kajiyama@seventh-well.com にメールで届く。
- 動くのは日本時間 5:00〜23:50 の間だけ。日付は今日か昨日だけ指定できる。
- 投稿済みのものは、どのURLを開いても二度とは出ない（二重投稿よけ）。

## 1. 状態を見る（何も動かない）
```
https://kajikeiba-autopost.kajisho5.workers.dev/stage?key=<KEY>
```
別の日を見る時は、最後に `&date=YYYYMMDD` を付ける。

返ってくる表示の見方:
- `stages.morning` が朝の予想、`stages.evening` が夜の答え合わせ。それぞれ `nar`（地方）と `jra`（中央）に分かれる。
- `fetch` が取得、`gen` が生成、`post` が投稿の状態。

`s` の意味:

| s | 意味 |
|---|---|
| ok | 済み |
| miss | 欠けあり（理由は `why`、欠けたレースは `missing`） |
| fail | 失敗 |
| none | 出すものが無い日（開催なしなど） |
| run | 動いている途中 |
| part | 途中まで投稿した |

`jobs` には、頼んだ工程とその結果が出る。

## 2. 工程ごとに動かす
例は中央の朝。次のように書き換えて使う:
- 地方にする → `mode=nar`
- 夜の答え合わせにする → `kind=evening`

### 取得だけ
予想（夜は結果）を作って保存し、件数を確かめる。画像は作らない。
```
https://kajikeiba-autopost.kajisho5.workers.dev/stage?key=<KEY>&kind=morning&mode=jra&step=fetch&go=1
```

### 生成だけ
保存した予想から画像と投稿文を作って保存する。予想は作り直さない。
```
https://kajikeiba-autopost.kajisho5.workers.dev/stage?key=<KEY>&kind=morning&mode=jra&step=gen&go=1
```

### 投稿だけ
保存した画像と文を X に出す。
```
https://kajikeiba-autopost.kajisho5.workers.dev/stage?key=<KEY>&kind=morning&mode=jra&step=post&go=1
```

### 足りない工程から最後まで
```
https://kajikeiba-autopost.kajisho5.workers.dev/stage?key=<KEY>&kind=morning&mode=jra&step=all&go=1
```

### 付け足せる指定
| 付け足し | 意味 |
|---|---|
| `&date=YYYYMMDD` | 対象の日（今日か昨日） |
| `&force=1` | 済んだ取得・生成をやり直す（投稿済みは、付けても出し直さない） |
| `&accept=1` | 取得で欠けが出て止まった時、欠けを承知のうえで生成・投稿へ進める |

## 3. 予想の件数を見る（合言葉は不要）
note 記事の下準備にも使える。
```
https://seventh-well.com/odds/predictions.php?action=summary&date=YYYYMMDD&mode=jra
```
場ごとに出る項目:

| 項目 | 意味 |
|---|---|
| `races` | レース数 |
| `pred` | 印を付けたレース |
| `skip` | 見送り |
| `noMarks` | 印が無い＝欠け |
| `results` | 結果が保存済み |
| `noResult` | 結果がまだのレース |

## 4. よくある場面
- **中央の予想を早く用意したい（note の下準備）**
  1. 朝7時より前に「取得だけ（jra）」を開く。
  2. 3の件数URLで、`pred` が入ったことを確かめる。

  ふだんも中央の開催日は 7:00・7:20・7:40・8:00 に自動で取得している。8:30 は保存した予想からそのまま画像を作って出す。
- **夜の投稿が「結果が取れていない」で止まった**
  1. 少し待ってから、夜の「足りない工程から最後まで」を開く（`kind=evening`）。
  2. 取消など、どうしても結果が入らないレースだけが残っている時は、同じURLに `&accept=1` を付けて開く。
- **投稿でXが断った（混雑など）**
  - 「投稿だけ」を開く。作り直さず、保存した画像で出す。
- **今どうなっているか分からない**
  - まず「状態を見る」を開く。

## 自動で動く時刻（日本時間）
| 時刻 | すること |
|---|---|
| 7:00・7:20・7:40・8:00 | 中央の取得（開催日だけ）。8:00 でも欠けていればメール |
| 8:30 | 朝の予想（地方・中央） |
| 9:00・9:20・9:40 | 朝の失敗のやり直し |
| 22:30 | 夜の答え合わせ |
| 22:50・23:10・23:40・23:50 | 夜の失敗のやり直し |
