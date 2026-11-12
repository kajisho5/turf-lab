/* 騎手・厩舎・父の索引が「実際の名前」で引けるかを検査する
 *
 * ★なぜ要るか★
 *   2026-07-30、_jkNorm が見習マークを**列挙して消す**方式で `▽` が漏れており、
 *   「▽笹川翼」（大井のトップ騎手・18,569騎乗）が null になっていた。
 *   索引には居るので**エラーも出ず、モデルは動き続け、精度だけ静かに落ちる**。
 *   本番の印を見ても気づけない壊れ方なので、機械で見張る。
 *
 * ★実装をコピーしない★
 *   deploy/tweet.html から _jkNorm / jkrOf / trrOf / _pedOf を**その場で抜き出して**使う。
 *   ここにコピーを書くと二重管理になり、本体を直してもテストが古い実装を検査する。
 *
 * 検査内容:
 *   1. 索引に実在するキーを、見習マーク付き・所属付きの形にしても引けるか
 *   2. 主要騎手（騎乗数の多い上位）が全員引けるか
 *   3. 中央の頭文字付き（C.ルメール）・4文字切り（佐々木大輔→佐々木大）が引けるか
 *
 * 使い方: node backtest/check_person_index.js   （npm run check に組込済み）
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.dirname(__dirname);
const D = (f) => path.join(ROOT, 'deploy', 'data', f);

function grabFn(src, name) {
  const i = src.indexOf('function ' + name);
  if (i < 0) throw new Error('tweet.html に関数が無い: ' + name);
  let depth = 0;
  for (let k = src.indexOf('{', i); k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (!depth) return src.slice(i, k + 1); }
  }
  throw new Error('関数の終端が見つからない: ' + name);
}

function loadJson(f) {
  try { return JSON.parse(fs.readFileSync(D(f), 'utf8')); }
  catch (e) { return null; }
}

const html = fs.readFileSync(path.join(ROOT, 'deploy', 'tweet.html'), 'utf8');
const body = ['_jkNorm', 'jkrOf', 'trrOf', '_pedOf'].map(n => grabFn(html, n)).join('\n');

const IDX = {
  jockeys: loadJson('jockeys.json'), trainers: loadJson('trainers.json'),
  sires: loadJson('sires.json'), jraJockeys: loadJson('jra_jockeys.json'),
  jraTrainers: loadJson('jra_trainers.json'),
};
const missing = Object.entries(IDX).filter(([, v]) => !v).map(([k]) => k);
if (missing.length) {
  console.log('索引が無い: ' + missing.join(', ')
    + '\n  作り直す: python backtest/build_jockey_index.py');
  process.exit(1);
}

function api(mode) {
  return new Function('MODE', '_LTR_JIDX', '_LTR_TIDX', '_LTR_SIDX', '_LTR_DIDX',
    body + '; return { jkrOf, trrOf, _pedOf, _jkNorm };')(
    mode,
    { nar: IDX.jockeys, jra: IDX.jraJockeys },
    { nar: IDX.trainers, jra: IDX.jraTrainers },
    { nar: IDX.sires }, {});
}
const nar = api('nar'), jra = api('jra');

/* netkeibaが騎手名に付ける見習マーク。★列挙漏れで壊れた実績があるので全部試す★ */
const MARKS = ['', '▲', '△', '☆', '▽', '★', '◇', '◆', '◎', '※', '☆ ', '　'];
let ng = 0;
const fail = (msg) => { console.log('  NG ' + msg); ng++; };

// 1) 索引の上位（騎乗数が多い＝実在が確実）をマーク付きで引く
function topKeys(idx, n) {
  return Object.entries(idx).sort((a, b) => b[1][1] - a[1][1]).slice(0, n).map(x => x[0]);
}
for (const [label, fn, idx] of [['地方騎手', nar.jkrOf, IDX.jockeys],
                                ['中央騎手', jra.jkrOf, IDX.jraJockeys]]) {
  for (const key of topKeys(idx, 12)) {
    for (const m of MARKS) {
      if (fn(m + key) == null) fail(`${label} 「${m}${key}」が引けない`);
    }
  }
}
// 2) 厩舎は「所属・名前」形式でも引けること（出馬表は "地方・田中淳" 等）
for (const [label, fn, idx, pre] of [['地方厩舎', nar.trrOf, IDX.trainers, '地方・'],
                                     ['中央厩舎', jra.trrOf, IDX.jraTrainers, '美浦・']]) {
  for (const key of topKeys(idx, 10)) {
    if (fn(key) == null) fail(`${label} 「${key}」が引けない`);
    if (fn(pre + key) == null) fail(`${label} 「${pre}${key}」が引けない`);
  }
}
// 3) 父（地方のみ）
for (const key of topKeys(IDX.sires, 10)) {
  if (nar._pedOf({ nar: IDX.sires }, key) == null) fail(`父 「${key}」が引けない`);
}
// 4) 中央の外国人騎手（頭文字付き）と4文字切り
for (const nm of ['C.ルメール', 'M.デムーロ', 'ルメール', 'モレイラ']) {
  if (jra.jkrOf(nm) == null) fail(`中央騎手 「${nm}」が引けない`);
}
// 5) 存在しない名前は null であること（何でも引けてしまうと誤った値を渡す）
for (const nm of ['ぜんぜんいない騎手', '']) {
  if (nar.jkrOf(nm) != null) fail(`実在しない「${nm}」に値が返る（引きすぎ）`);
}

if (ng) {
  console.log(`\n${ng}件の照合失敗。tweet.html の _jkNorm / *Of を確認`
    + '（マークの列挙漏れ・名前の切り方のズレが原因になりやすい）');
  process.exit(1);
}
console.log(`OK  騎手/厩舎/父の索引照合 ${MARKS.length}種のマーク × 上位キーで全一致`);
