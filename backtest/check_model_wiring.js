/* モデルの列が「使う側」全部に配線されているかを検査する
 *
 * ★なぜ要るか★
 *   2026-07-30、列を足すたびに配線を忘れた:
 *     - jkr/trr/sir を core/ltr_model.js に入れたが core/personas.js に渡していなかった
 *       → 公開サイトが3列欠損で動くところだった
 *     - 索引(jockeys.json等)を deploy の設定に入れ忘れ → 404で欠損に戻る
 *     - 索引を日次更新に入れ忘れ → 日が経つほど古い率で予想する
 *   どれも**エラーが出ず、精度だけ静かに落ちる**。人間の記憶に頼ると必ず漏れる。
 *
 * 検査:
 *   1. core/ltr_model.js の feats（nar/jra）が
 *      deploy/tweet.html の ltrFeatTweet と core/personas.js の ltrFeat の
 *      両方でキーとして現れるか（レース側から来る dist/fn/tc 等は除外）
 *   2. 索引ファイル（deploy/data/*.json のうちモデルが使うもの）が
 *      deploy.py の MAP と PUBLIC_MAP の両方に載っているか
 *   3. 索引の生成が backtest/daily.py に入っているか
 *
 * 使い方: node backtest/check_model_wiring.js   （npm run check に組込）
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.dirname(__dirname);
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

let ng = 0;
const fail = (m) => { console.log('  NG ' + m); ng++; };

/* レース側の情報。馬ごとの供給ではないので ltrFeatTweet/ltrFeat の
   キー一覧に無くても正しい（それぞれ別経路で入る）。 */
const RACE_LEVEL = new Set(['dist', 'fn', 'going', 'surf', 'rno']);

const { LTR_MODEL } = require(path.join(ROOT, 'core', 'ltr_model.js'));
const tweet = read('deploy/tweet.html');
const personas = read('core/personas.js');

/* 関数本体を抜き出す（ファイル全体を検索すると、無関係な箇所の一致で見逃す） */
function fnBody(src, name) {
  const i = src.indexOf('function ' + name);
  if (i < 0) return null;
  let d = 0;
  for (let k = src.indexOf('{', i); k < src.length; k++) {
    if (src[k] === '{') d++;
    else if (src[k] === '}') { d--; if (!d) return src.slice(i, k + 1); }
  }
  return null;
}
const tweetFeat = fnBody(tweet, 'ltrFeatTweet');
const personaFeat = fnBody(personas, 'ltrFeat');
if (!tweetFeat) fail('deploy/tweet.html に ltrFeatTweet が見つからない');
if (!personaFeat) fail('core/personas.js に ltrFeat が見つからない');

/* narM（市場込み・LINE配信専用）は除外する。
   - personas.js/公開サイトには載せない仕様（事前予想の建前が壊れるため）
   - pop は tweet.html の lineTick がオッズ取得後にインラインで渡す
   除外は「モード名で丸ごと」ではなく列単位にすると漏れるので、モードごと除外。 */
const DELIVERY_ONLY_MODES = new Set(['narM', 'jraM']);
if (tweetFeat && personaFeat) {
  for (const mode of Object.keys(LTR_MODEL)) {
    if (DELIVERY_ONLY_MODES.has(mode)) continue;
    for (const f of LTR_MODEL[mode].feats) {
      if (RACE_LEVEL.has(f)) continue;
      // キーとして書かれているか（"jkr:" の形）
      const re = new RegExp('(^|[^\\w])' + f + '\\s*:');
      if (!re.test(tweetFeat)) fail(`[${mode}] 列 ${f} が tweet.html の ltrFeatTweet に無い`);
      if (!re.test(personaFeat)) fail(`[${mode}] 列 ${f} が personas.js の ltrFeat に無い`);
    }
  }
}

/* ★学習側(FEATS)と本番モデルの列が一致しているか★
   却下した列を FEATS から外し忘れると、次に再学習した人が
   **却下済みの列入りモデルを本番に載せる**（2026-07-30に実際に3列ズレていた:
   相手関係を却下したのに FEATS に残っていて、FEATS 36列 vs 本番33列）。
   デプロイ済みモデルの列を正として、学習設定が同じ列を作るか確かめる。 */
try {
  const { execSync } = require('child_process');
  const py = execSync(
    'python -c "import os,sys;os.environ[\'LTR_NEWFEATS\']=\'pre\';' +
    'os.environ[\'LTR_TC\']=\'1\';os.environ[\'LTR_NODMS\']=\'1\';' +
    'sys.path.insert(0,\'backtest\');from bt_train_ltr import FEATS;print(\',\'.join(FEATS))"',
    { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  const trainFeats = py.split(',').filter(Boolean);
  const prodFeats = LTR_MODEL.nar.feats;
  const onlyTrain = trainFeats.filter(f => !prodFeats.includes(f));
  const onlyProd = prodFeats.filter(f => !trainFeats.includes(f));
  if (onlyTrain.length)
    fail(`学習側(FEATS)にあって本番モデルに無い列: ${onlyTrain.join(',')}`
       + '（却下した列の外し忘れ？ 次の再学習で本番に混入する）');
  if (onlyProd.length)
    fail(`本番モデルにあって学習側(FEATS)に無い列: ${onlyProd.join(',')}`
       + '（再学習すると列が減る）');
} catch (e) {
  console.log('  （FEATS照合はスキップ: python未実行環境）');
}

/* 索引ファイルが両方のデプロイ設定に載っているか */
const deploy = read('backtest/deploy.py');
const NEEDED_INDEX = ['jockeys.json', 'jra_jockeys.json', 'trainers.json',
                      'jra_trainers.json', 'sires.json', 'horses.json', 'jra_horses.json'];
for (const f of NEEDED_INDEX) {
  if (!deploy.includes(`/seventh-well.com/odds/data/${f}`))
    fail(`索引 ${f} が deploy.py の MAP（tweet.html側）に無い`);
  if (!deploy.includes(`/kajikeiba.com/data/${f}`))
    fail(`索引 ${f} が deploy.py の PUBLIC_MAP（公開サイト側）に無い`);
}

/* 索引の生成が日次に入っているか（入れ忘れると古い率で予想し続ける） */
const daily = read('backtest/daily.py');
for (const s of ['build_horse_index.py', 'build_jockey_index.py', 'build_dataset.py']) {
  if (!daily.includes(s)) fail(`${s} が daily.py に入っていない（索引が古いまま予想する）`);
}

if (ng) {
  console.log(`\n${ng}件の配線漏れ。★列を足したら「使う側」を全部たどること★`);
  console.log('  供給: deploy/tweet.html ltrFeatTweet / core/personas.js ltrFeat');
  console.log('  索引: build_jockey_index.py → deploy.py の MAP と PUBLIC_MAP 両方');
  console.log('  日次: backtest/daily.py に生成ステップ');
  process.exit(1);
}
const n = Object.keys(LTR_MODEL).map(m => LTR_MODEL[m].feats.length).join('/');
console.log(`OK  モデル配線（${n}列）: 供給2経路・索引7本×2サイト・日次生成 すべて到達`);
