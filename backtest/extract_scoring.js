/* tweet.html から採点まわりを AST で正確に切り出す
 *
 * ★なぜ正規表現ではだめか★
 *   前回 `名前(` を数えたら 116定義・196KB になった。実際には
 *   配列の添字 `x[i]`、オブジェクトのキー、コメント内の記述まで拾っており、
 *   描画・ツイート文生成・PWA まで巻き込んでいた。
 *   逆に、参照渡し（map(parsePastRace) のように括弧が付かない形）は
 *   取りこぼす。**多すぎと少なすぎが同時に起きる**のが正規表現の駄目なところ。
 *
 *   AST なら「識別子として参照されたか」を正しく判定できる。
 *   kochi.html を4回壊した原因はここなので、道具を変える。
 *
 * ★出力は2つ★
 *   1) 依存の一覧（何を持っていくか）
 *   2) 実際に切り出したソース（定義順を保つ）
 *
 * 使い方:
 *   node backtest/extract_scoring.js            # 一覧だけ
 *   node backtest/extract_scoring.js --write    # core/scoring.js を書き出す
 */
const fs = require("fs");
const path = require("path");
const acorn = require("acorn");
const walk = require("acorn-walk");

const ROOT = path.dirname(__dirname);
const SRC = path.join(ROOT, "deploy", "tweet.html");
const OUT = path.join(ROOT, "core", "scoring.js");

/* 採点に必要な入口。ここから辿れるものだけを持っていく */
/* ★parseShutuba も入口にする★
   スコア関数だけ抽出しても、GBMが要求する entries（各馬の past 付き）を
   作れないので、レースページで GBM を出せなかった。
   parseShutuba / parsePastRace は tweet.html にあるので、
   コピーせず**抽出器の入口を足して**取り込む。 */
const ENTRY = ["fundamentalScore", "gbmScore", "fullBreakdown", "factorW",
  "parseShutuba", "parsePastRace",
               "scoreBreakdown", "GBM_MODEL"];

/* ブラウザ/JS の組み込み。これらは持っていかない */
const GLOBALS = new Set(`
Object Array String Number Boolean Symbol BigInt Function Math JSON Date RegExp
Error TypeError RangeError Map Set WeakMap WeakSet Promise Proxy Reflect Intl
parseInt parseFloat isNaN isFinite encodeURIComponent decodeURIComponent
globalThis undefined NaN Infinity console window document navigator location
localStorage sessionStorage fetch setTimeout setInterval clearTimeout
requestAnimationFrame structuredClone btoa atob TextEncoder TextDecoder
Uint8Array Float64Array Int32Array ArrayBuffer performance crypto alert
DOMParser Image Blob URL AbortController
`.trim().split(/\s+/));

function extractJs(html) {
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m, out = [];
  while ((m = re.exec(html))) {
    if (/\bsrc\s*=/i.test(m[1])) continue;
    out.push(m[2]);
  }
  return out.join("\n;\n");
}

/* トップレベルの宣言だけを集める（関数の中の変数は対象外） */
function topLevelDecls(ast, code) {
  const decls = new Map();   // 名前 -> {start, end}
  for (const node of ast.body) {
    if (node.type === "FunctionDeclaration" && node.id) {
      decls.set(node.id.name, { start: node.start, end: node.end, kind: "function" });
    } else if (node.type === "VariableDeclaration") {
      for (const d of node.declarations) {
        if (d.id.type === "Identifier") {
          // 宣言子ごとに切り出せるよう、kind を付けて範囲を持つ
          decls.set(d.id.name, {
            start: node.start, end: node.end,
            shared: node.declarations.length > 1,
            kind: node.kind        // let / var / const
          });
        }
      }
    } else if (node.type === "ClassDeclaration" && node.id) {
      decls.set(node.id.name, { start: node.start, end: node.end, kind: "class" });
    }
  }
  return decls;
}

/* そのノードの内側で宣言されている名前（引数・var/let/const・内部関数・catch）
   ★これを引かないと、ローカル変数が「外部依存」として大量に誤検出される★
   実際 i / tmp / ctx のような名前が90個以上ぶら下がって、
   本当に足りないものが埋もれてしまった。 */
function localsIn(node) {
  const out = new Set();
  const addPat = (n) => {
    if (!n) return;
    switch (n.type) {
      case "Identifier": out.add(n.name); break;
      case "ObjectPattern": n.properties.forEach(p => addPat(p.value || p.argument)); break;
      case "ArrayPattern": n.elements.forEach(addPat); break;
      case "AssignmentPattern": addPat(n.left); break;
      case "RestElement": addPat(n.argument); break;
    }
  };
  walk.full(node, (n) => {
    switch (n.type) {
      case "VariableDeclarator": addPat(n.id); break;
      case "FunctionDeclaration":
      case "FunctionExpression":
      case "ArrowFunctionExpression":
        if (n.id) out.add(n.id.name);
        n.params.forEach(addPat);
        break;
      case "ClassDeclaration":
      case "ClassExpression": if (n.id) out.add(n.id.name); break;
      case "CatchClause": addPat(n.param); break;
    }
  });
  return out;
}

/* あるノードの中で「参照されている識別子」を集める（宣言側・プロパティ名は除く） */
function refsIn(node) {
  const out = new Set();
  walk.ancestor(node, {
    Identifier(n, _s, anc) {
      const p = anc[anc.length - 2];
      if (!p) return;
      if (p.type === "MemberExpression" && p.property === n && !p.computed) return;
      if (p.type === "Property" && p.key === n && !p.computed) return;
      if ((p.type === "MethodDefinition" || p.type === "PropertyDefinition")
          && p.key === n && !p.computed) return;
      if (p.type === "VariableDeclarator" && p.id === n) return;
      if ((p.type === "FunctionDeclaration" || p.type === "FunctionExpression"
           || p.type === "ArrowFunctionExpression" || p.type === "ClassDeclaration")
          && p.id === n) return;
      if (p.type === "LabeledStatement" || p.type === "BreakStatement"
          || p.type === "ContinueStatement") return;
      out.add(n.name);
    }
  });
  // 内側で宣言されている名前は外部依存ではない
  for (const l of localsIn(node)) out.delete(l);
  return out;
}

function main() {
  const write = process.argv.includes("--write");
  const html = fs.readFileSync(SRC, "utf8");
  const code = extractJs(html);
  const ast = acorn.parse(code, { ecmaVersion: "latest", locations: true });

  const decls = topLevelDecls(ast, code);
  console.log(`tweet.html のトップレベル定義: ${decls.size}個 / JS全体 ${(code.length/1024).toFixed(0)}KB`);

  // 各定義の本体ノードを引ける表
  const nodeOf = new Map();
  for (const node of ast.body) {
    if (node.type === "FunctionDeclaration" && node.id) nodeOf.set(node.id.name, node);
    else if (node.type === "VariableDeclaration") {
      for (const d of node.declarations) {
        if (d.id.type === "Identifier") nodeOf.set(d.id.name, node);
      }
    } else if (node.type === "ClassDeclaration" && node.id) nodeOf.set(node.id.name, node);
  }

  // 入口から推移閉包を取る
  const need = new Set();
  const queue = ENTRY.filter(n => decls.has(n));
  const missingEntry = ENTRY.filter(n => !decls.has(n));
  while (queue.length) {
    const n = queue.shift();
    if (need.has(n)) continue;
    need.add(n);
    const node = nodeOf.get(n);
    if (!node) continue;
    for (const r of refsIn(node)) {
      if (r === n) continue;
      if (GLOBALS.has(r)) continue;
      if (!decls.has(r)) continue;      // 未定義＝組み込みか外部
      if (!need.has(r)) queue.push(r);
    }
  }

  // 依存の外にあるが参照されている名前（＝持っていけないもの）を洗う
  const outside = new Set();
  for (const n of need) {
    const node = nodeOf.get(n);
    if (!node) continue;
    for (const r of refsIn(node)) {
      if (need.has(r) || GLOBALS.has(r) || decls.has(r)) continue;
      outside.add(r);
    }
  }

  const list = [...need].filter(n => decls.has(n));
  // 元の並び順を保つ（定義順に依存している箇所があるため）
  list.sort((a, b) => decls.get(a).start - decls.get(b).start);
  const bytes = list.reduce((s, n) => {
    const d = decls.get(n); return s + (d.end - d.start);
  }, 0);

  console.log(`\n必要な定義: ${list.length}個 / ${(bytes/1024).toFixed(0)}KB`);
  if (missingEntry.length) console.log(`!! 入口が見つからない: ${missingEntry.join(" ")}`);
  console.log(`\n持っていくもの:\n  ${list.join(" ")}`);
  if (outside.size) {
    console.log(`\n★外部に依存している名前（グローバル扱い・要確認）:\n  ${[...outside].sort().join(" ")}`);
  }

  if (!write) { console.log("\n（--write を付けると core/scoring.js を書き出す）"); return; }

  // 同じ VariableDeclaration を共有する宣言は1回だけ出す
  const emitted = new Set();
  const parts = [];
  for (const n of list) {
    const d = decls.get(n);
    const key = `${d.start}:${d.end}`;
    if (emitted.has(key)) continue;
    emitted.add(key);
    parts.push(code.slice(d.start, d.end));
  }

  const header = `/* 採点の共通コア — tweet.html から切り出したもの
 *
 * ★このファイルが唯一の定義場所★
 *   以前は tweet.html から関数をコピーして kochi.html を作っていた。
 *   写し漏れが本番で未定義エラーになり、v357/v359/v360/v364 と
 *   4回連鎖して本番が動かない期間が発生した。コピーをやめる。
 *
 * ★切り出しは backtest/extract_scoring.js が AST で行う★
 *   手で選ぶと必ず漏れる。正規表現でも漏れる（参照渡しを取りこぼし、
 *   配列の添字を誤検出する）。依存の判定は acorn の AST で行っている。
 *
 * ★切り出し後は必ず照合する★
 *   backtest/verify_scoring.js が、tweet.html 内の実装とこのファイルの
 *   実装に同じ入力を与え、出力が一致するかを確認する。
 *   一致しないまま公開すると「移植したつもりで別物」になる。
 *
 * 生成日時: ${new Date().toISOString()}
 * 定義数: ${list.length} / サイズ: ${(bytes/1024).toFixed(0)}KB
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SCORING = factory();
}(typeof self !== 'undefined' ? self : this, function () {
'use strict';
`;
  /* ★書き換わる変数は値ではなくアクセサで公開する★
     MODE は「nar と jra のどちらの決定木を使うか」を決めている。
     値のまま返すとエクスポート時点で固定され、呼び出し側が
     scoring.MODE = "jra" としても中身は nar のままになる。
     実際これで GBM のロジットが全レース同じ値になり、
     tweet.html 側と 2,721件 食い違った。 */
  const mutable = list.filter(n => ["let", "var"].includes(decls.get(n).kind));
  const fixed = list.filter(n => !mutable.includes(n));
  const NL = ",\n";
  const accessors = mutable
    .map(n => `  get ${n}(){ return ${n}; }, set ${n}(v){ ${n} = v; }`)
    .join(NL);
  const body = fixed.map(n => `  ${n}: ${n}`).join(NL)
             + (mutable.length ? NL + accessors : "");
  const footer = "\nreturn {\n" + body + "\n};\n}));\n";
  console.log("\n書き換わる変数（アクセサで公開）: " + (mutable.join(" ") || "なし"));
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, header + parts.join("\n\n") + footer, "utf8");
  console.log(`\n書き出し: ${path.relative(ROOT, OUT)}  ${(fs.statSync(OUT).size/1024).toFixed(0)}KB`);
}

main();
