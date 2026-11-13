/* ◎の「強み」1行（deploy/tweet.html の strengthLine）の決まりの試験。数字は全部作りもの。
   使い方: node backtest/check_strength_line.js */
const fs = require('fs'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'deploy', 'tweet.html'), 'utf8');
const a = html.indexOf('function strengthLine'), b = html.indexOf('/* ===== 朝の1枚目', a);
if (a < 0 || b < 0) { console.log('!! strengthLine が見つからない'); process.exit(1); }
const strengthLine = new Function(html.slice(a, b) + '; return strengthLine;')();
let ok = 0, ng = 0; const eq = (n, x, y) => { x === y ? ok++ : (ng++, console.log('NG', n, x, y)); };
const base = { 1: { sva: 0.3, btf: 0.1, afa: 0.2, jkr: 0.3 }, 2: { sva: 0.2, btf: 0.3, afa: 0.9, jkr: 0.6 }, 3: { sva: 0.1, btf: 0.2, afa: 0.1, jkr: 0.2 },
  4: { sva: 0.0, btf: 0.0, afa: 0.0, jkr: 0.1 }, 5: { sva: -0.1, btf: -0.1, afa: -0.1, jkr: 0.1 } };
eq('時計1位', strengthLine(base, 1, null), '近走の時計がメンバー1位');
eq('持ち時計1位（時計は1位でない馬）', strengthLine(base, 2, null), 'この距離の持ち時計が1位');
eq('上がり最速', strengthLine({ ...base, 2: { ...base[2], btf: 0.05 } }, 2, null), '近走の上がりがメンバー最速');
eq('この場', strengthLine(base, 3, [75, 8]), 'この場で3着内 8走中6回');
eq('この場は5走以上', strengthLine(base, 3, [100, 4]), null);
eq('この場は6割以上', strengthLine(base, 3, [50, 10]), null);
eq('騎手', strengthLine({ ...base, 2: { sva: 0, btf: 0, afa: 0, jkr: 0.6 } }, 2, [40, 10]), '騎手の3着内率 60%');
eq('当てはまらない', strengthLine(base, 4, null), null);
eq('同じ値の1位は出さない', strengthLine({ ...base, 2: { ...base[2], sva: 0.3 } }, 1, null), null);
eq('値のある馬が4頭なら出さない', strengthLine({ 1: { sva: 1 }, 2: { sva: 0 }, 3: { sva: 0 }, 4: { sva: 0 }, 5: {} }, 1, null), null);
console.log(ng ? '!! 強みの決まり NG ' + ng : 'OK  強みの決まり ' + ok + '件');
process.exit(ng ? 1 : 0);
