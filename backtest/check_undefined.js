/* 未定義の識別子を検出する（デプロイ前の必須チェック）
 *
 * ★なぜ要るか★
 *   2026-07-19 に本番の kochi.html が完全に動かなくなった。原因は4件とも同じ:
 *     v357: looksValid
 *     v359: parsePastRace / classLevelFromBlock / classLevelName / trackNameOfRid /
 *           post / TURN_BY_TRACK / NAR_TRACK / JRA_TRACK / NAR_JUSHO / state
 *     v360: starsBelow（tweet.html にも同じ穴があった）
 *   node -e "new Function(...)" は構文チェックなので全部素通りする。
 *   実行するまで分からず、catch(e){} に握り潰されて「解析に失敗」としか出なかった。
 *
 * ★正規表現版(check_undefined.py)は失敗した★
 *   誤検出63件。フォント文字列 "Noto Sans JP" の中身まで識別子として拾った。
 *   ここでは acorn で AST を取り、スコープを正しく追う。
 *
 * 使い方:
 *   node backtest/check_undefined.js                    # deploy/*.html 全部
 *   node backtest/check_undefined.js deploy/kochi.html  # 個別
 *   終了コード 0=問題なし / 1=未定義あり
 */
const fs = require("fs");
const path = require("path");
const acorn = require("acorn");
const walk = require("acorn-walk");

const ROOT = path.dirname(__dirname);

// ブラウザ/JS の組み込み。ここに無いものが「未定義」として報告される。
const GLOBALS = new Set(`
window document navigator location history screen console alert confirm prompt
ltrScore LTR_MODEL ltrScoreT LTR_MODEL_T
setTimeout setInterval clearTimeout clearInterval requestAnimationFrame cancelAnimationFrame
queueMicrotask structuredClone reportError getComputedStyle matchMedia
fetch Request Response Headers FormData Blob File FileReader URL URLSearchParams
XMLHttpRequest WebSocket EventSource AbortController AbortSignal
localStorage sessionStorage indexedDB caches crypto performance
Image Audio Option Event CustomEvent MouseEvent KeyboardEvent TouchEvent
DOMParser XMLSerializer NodeFilter MutationObserver IntersectionObserver ResizeObserver
HTMLElement HTMLCanvasElement HTMLImageElement Element Node Text DocumentFragment
CanvasRenderingContext2D Path2D ImageData OffscreenCanvas MediaRecorder
Object Array String Number Boolean Symbol BigInt Function
Math JSON Date RegExp Error TypeError RangeError SyntaxError ReferenceError EvalError URIError
Map Set WeakMap WeakSet Promise Proxy Reflect Intl FontFace
ArrayBuffer SharedArrayBuffer DataView Atomics
Int8Array Uint8Array Uint8ClampedArray Int16Array Uint16Array Int32Array Uint32Array
Float32Array Float64Array BigInt64Array BigUint64Array
TextEncoder TextDecoder
parseInt parseFloat isNaN isFinite encodeURIComponent decodeURIComponent encodeURI decodeURI
escape unescape btoa atob globalThis undefined NaN Infinity
self top parent frames closed opener arguments
devicePixelRatio ClipboardItem ClipboardEvent DragEvent Notification
`.trim().split(/\s+/));

/* ★誤検出だった実名★ ここは「デプロイ前チェックで毎回止まらないようにする」ためのリスト。
   本物のバグではないと確認済み:
   - module: race.html の typeof module!=='undefined' はCommonJS判定の定型ガードで安全
     （typeof は未定義変数に対しても例外を投げないため、本チェッカーはそれを判定していない）
   - NKPast: race.html が <script src="/core/netkeiba_past.js"> で外部読み込みしている
     グローバル。本チェッカーは src 付き<script>の中身を追わないため未定義に見えるだけ。 */
const KNOWN_FALSE_POSITIVES = new Set(["module", "exports", "require", "NKPast"]);
for (const n of KNOWN_FALSE_POSITIVES) GLOBALS.add(n);

/* HTML から <script> の中身を取り出す（src付きは対象外） */
function extractJs(html) {
  const out = [];
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = re.exec(html))) {
    if (/\bsrc\s*=/i.test(m[1])) continue;   // 外部読み込みは中身が無い
    out.push(m[2]);
  }
  return out.join("\n;\n");
}

/* スコープを積みながら、宣言された名前を集める */
function collectDeclared(ast) {
  const declared = new Set();

  const addPattern = (node) => {
    if (!node) return;
    switch (node.type) {
      case "Identifier": declared.add(node.name); break;
      case "ObjectPattern":
        node.properties.forEach(p => addPattern(p.value || p.argument)); break;
      case "ArrayPattern":
        node.elements.forEach(e => addPattern(e)); break;
      case "AssignmentPattern": addPattern(node.left); break;
      case "RestElement": addPattern(node.argument); break;
    }
  };

  walk.full(ast, (node) => {
    switch (node.type) {
      case "VariableDeclarator": addPattern(node.id); break;
      case "FunctionDeclaration":
      case "FunctionExpression":
      case "ArrowFunctionExpression":
        if (node.id) declared.add(node.id.name);
        node.params.forEach(addPattern);
        break;
      case "ClassDeclaration":
      case "ClassExpression":
        if (node.id) declared.add(node.id.name);
        break;
      case "CatchClause": addPattern(node.param); break;
      case "LabeledStatement": declared.add(node.label.name); break;
      case "ImportDefaultSpecifier":
      case "ImportNamespaceSpecifier":
      case "ImportSpecifier": declared.add(node.local.name); break;
    }
  });
  return declared;
}

/* 参照されている識別子を集める（プロパティ名・オブジェクトキー・ラベルは除外） */
function collectReferenced(ast) {
  const refs = new Map();   // name -> 出現行の配列
  walk.ancestor(ast, {
    Identifier(node, _state, ancestors) {
      const parent = ancestors[ancestors.length - 2];
      if (!parent) return;
      // obj.foo の foo（計算プロパティでない）
      if (parent.type === "MemberExpression" && parent.property === node && !parent.computed) return;
      // {foo: 1} のキー
      if (parent.type === "Property" && parent.key === node && !parent.computed) return;
      // {foo(){}} のメソッド名 / class のメソッド名
      if (parent.type === "MethodDefinition" || parent.type === "PropertyDefinition") {
        if (parent.key === node && !parent.computed) return;
      }
      // 宣言側の名前
      if (parent.type === "VariableDeclarator" && parent.id === node) return;
      if ((parent.type === "FunctionDeclaration" || parent.type === "FunctionExpression" ||
           parent.type === "ArrowFunctionExpression" || parent.type === "ClassDeclaration" ||
           parent.type === "ClassExpression") && parent.id === node) return;
      if (parent.type === "LabeledStatement" || parent.type === "BreakStatement" ||
          parent.type === "ContinueStatement") return;
      // 関数の仮引数
      if ((parent.type === "FunctionDeclaration" || parent.type === "FunctionExpression" ||
           parent.type === "ArrowFunctionExpression") && parent.params.includes(node)) return;

      if (!refs.has(node.name)) refs.set(node.name, []);
      refs.get(node.name).push(node.loc ? node.loc.start.line : 0);
    }
  });
  return refs;
}

function check(file) {
  const html = fs.readFileSync(file, "utf8");
  const js = extractJs(html);
  if (!js.trim()) return { skipped: true };

  let ast;
  try {
    ast = acorn.parse(js, { ecmaVersion: "latest", locations: true, allowReturnOutsideFunction: true });
  } catch (e) {
    return { parseError: `${e.message}` };
  }

  const declared = collectDeclared(ast);
  const refs = collectReferenced(ast);

  const undef = [];
  for (const [name, lines] of refs) {
    if (declared.has(name) || GLOBALS.has(name)) continue;
    undef.push({ name, count: lines.length, first: lines[0] });
  }
  undef.sort((a, b) => b.count - a.count);
  return { undef };
}

function main() {
  let targets = process.argv.slice(2);
  if (!targets.length) {
    const d = path.join(ROOT, "deploy");
    targets = fs.readdirSync(d).filter(f => f.endsWith(".html")).sort()
      .map(f => path.join(d, f));
  }
  let bad = 0;
  for (let p of targets) {
    if (!path.isAbsolute(p)) p = path.join(ROOT, p);
    const rel = path.relative(ROOT, p);
    const r = check(p);
    if (r.skipped) { console.log(`[--] ${rel}  （インラインJSなし）`); continue; }
    if (r.parseError) { console.log(`[ER] ${rel}  パース失敗: ${r.parseError}`); bad++; continue; }
    if (r.undef.length) {
      bad++;
      console.log(`\n[NG] ${rel}  未定義の識別子 ${r.undef.length}件`);
      for (const u of r.undef) {
        console.log(`     ${u.name.padEnd(28)} ${String(u.count).padStart(3)}箇所  (最初: ${u.first}行目)`);
      }
    } else {
      console.log(`[OK] ${rel}`);
    }
  }
  console.log();
  if (bad) {
    console.log(`!! ${bad}ファイルに問題がある。デプロイ前に解消すること。`);
    console.log(`   誤検出だと判断した名前は GLOBALS に追加する。`);
    process.exit(1);
  }
  console.log("未定義の識別子なし。");
}

main();
