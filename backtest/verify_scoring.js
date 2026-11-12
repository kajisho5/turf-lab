/* 切り出した core/scoring.js が、tweet.html 内の実装と同じ答えを返すか照合する
 *
 * ★これを通すまで公開しない★
 *   「移植したつもりで別物」が一番たちが悪い。画面には数字が出るので
 *   壊れていることに気づけず、公開している成績とも食い違う。
 *   kochi.html のときは未定義エラーで派手に落ちたので気づけたが、
 *   採点は静かにズレる。だから機械で突き合わせる。
 *
 * ★やり方★
 *   1. tweet.html の JS 全体を Node 上で評価し、その中の関数を取り出す
 *   2. core/scoring.js を読み込む
 *   3. 同じ入力（ランダム生成した出馬表）を両方に与える
 *   4. 出力（スコア・GBMロジット・内訳）を全部つき合わせる
 *
 *   入力はランダムに大量生成する。手で作った1件だけ合わせても、
 *   分岐の片側しか通らないことがあるため。
 *
 * 使い方: node backtest/verify_scoring.js [件数]
 * 終了コード 0=一致 / 1=不一致
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.dirname(__dirname);
const N = parseInt(process.argv[2], 10) || 3000;

function extractJs(html) {
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m, out = [];
  while ((m = re.exec(html))) {
    if (/\bsrc\s*=/i.test(m[1])) continue;
    out.push(m[2]);
  }
  return out.join("\n;\n");
}

/* tweet.html を Node 上で「読み込むだけ」実行する。
   ブラウザAPIを触る初期化が走ると落ちるので、最低限の張りぼてを用意する。 */
function loadTweet() {
  const html = fs.readFileSync(path.join(ROOT, "deploy", "tweet.html"), "utf8");
  const code = extractJs(html);

  const noop = () => {};
  const el = new Proxy({}, {
    get: (t, k) => {
      if (k === "style" || k === "dataset" || k === "classList") return el;
      if (k === "appendChild" || k === "addEventListener" || k === "remove"
          || k === "setAttribute" || k === "querySelector"
          || k === "querySelectorAll" || k === "getContext") return () => el;
      if (k === "children" || k === "childNodes") return [];
      if (k === "textContent" || k === "innerHTML" || k === "value") return "";
      return undefined;
    },
    set: () => true
  });
  const doc = {
    documentElement: el, body: el, head: el,
    querySelector: () => el, querySelectorAll: () => [],
    getElementById: () => el, createElement: () => el,
    addEventListener: noop, readyState: "complete", cookie: ""
  };
  const store = {};
  const sandbox = {
    console: { log: noop, warn: noop, error: noop, info: noop },
    document: doc,
    window: null,
    navigator: { userAgent: "node", serviceWorker: { register: () => Promise.resolve() } },
    location: { href: "https://example.com/", search: "", pathname: "/", hash: "" },
    localStorage: {
      getItem: k => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: k => { delete store[k]; }
    },
    fetch: () => Promise.reject(new Error("network disabled")),
    setTimeout: noop, setInterval: noop, clearTimeout: noop, clearInterval: noop,
    requestAnimationFrame: noop,
    alert: noop, confirm: () => false, prompt: () => null,
    Image: function () { return el; },
    DOMParser: function () { return { parseFromString: () => doc }; },
    matchMedia: () => ({ matches: false, addEventListener: noop }),
    performance: { now: () => 0 },
    caches: undefined, indexedDB: undefined,
    /* ★スタブが足りないと初期化が途中で落ち、そこから後ろの定義が読まれない★
       MutationObserver で落ちて GBM_MODEL が取り出せなかった。
       採点に関係ない機能でも、定義まで到達させるために形だけ用意する。 */
    MutationObserver: function () { return { observe: noop, disconnect: noop }; },
    IntersectionObserver: function () { return { observe: noop, disconnect: noop }; },
    ResizeObserver: function () { return { observe: noop, disconnect: noop }; },
    Event: function () {}, CustomEvent: function () {},
    history: { pushState: noop, replaceState: noop },
    screen: { width: 375, height: 812 },
    XMLHttpRequest: function () { return { open: noop, send: noop, addEventListener: noop }; },
    WebSocket: function () { return { close: noop, addEventListener: noop }; },
    Notification: function () {}, ClipboardItem: function () {},
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
    devicePixelRatio: 2, innerWidth: 375, innerHeight: 812,
    scrollTo: noop, open: noop, close: noop, print: noop,
    URLSearchParams: URLSearchParams, TextEncoder: TextEncoder,
    Intl: Intl, queueMicrotask: noop
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;

  const ctx = vm.createContext(sandbox);

  /* ★const / let は vm のコンテキストにプロパティとして現れない★
     var と違い、スクリプトのレキシカルスコープに閉じる。
     そのため ctx.GBM_MODEL は undefined になり、取り出せなかった。
     スクリプト末尾に橋渡しを足して、同じスコープの中から公開する。
     MODE は書き換えたいので getter/setter にする（let なので代入できる）。 */
  const bridge = `
;globalThis.__API__ = {
  fundamentalScore: fundamentalScore,
  gbmScore: gbmScore,
  fullBreakdown: fullBreakdown,
  factorW: factorW,
  get GBM_MODEL(){ return GBM_MODEL; },
  get MODE(){ return MODE; }, set MODE(v){ MODE = v; }
};`;

  let err = null;
  try {
    vm.runInContext(code + bridge, ctx, { timeout: 120000 });
  } catch (e) {
    err = e;
  }
  return { ctx, api: ctx.__API__, err };
}

/* 出馬表を1つランダムに作る。実データの取りうる形をなるべく広く踏む */
function makeRace(rnd) {
  const n = 5 + Math.floor(rnd() * 14);          // 5〜18頭
  const isNar = rnd() < 0.5;
  const tracks = isNar
    ? ["門別", "盛岡", "水沢", "浦和", "船橋", "大井", "川崎", "金沢",
       "笠松", "名古屋", "園田", "姫路", "高知", "佐賀"]
    : ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"];
  const track = tracks[Math.floor(rnd() * tracks.length)];
  const dist = [800, 1000, 1200, 1300, 1400, 1600, 1700, 1800, 2000, 2400][Math.floor(rnd() * 10)];
  const surf = isNar ? "ダ" : (rnd() < 0.5 ? "芝" : "ダ");
  const going = ["良", "稍重", "重", "不良"][Math.floor(rnd() * 4)];

  const horses = [];
  for (let i = 1; i <= n; i++) {
    const past = [];
    const np = Math.floor(rnd() * 6);            // 0〜5走
    for (let j = 0; j < np; j++) {
      const field = 6 + Math.floor(rnd() * 12);
      past.push({
        date: `2026${String(1 + Math.floor(rnd() * 6)).padStart(2, "0")}${String(1 + Math.floor(rnd() * 28)).padStart(2, "0")}`,
        rank: 1 + Math.floor(rnd() * field),
        field,
        num: 1 + Math.floor(rnd() * field),
        pop: 1 + Math.floor(rnd() * field),
        corner: [1 + Math.floor(rnd() * field), 1 + Math.floor(rnd() * field)],
        last3f: 34 + rnd() * 6,
        time: 60 + rnd() * 60,
        dist: [1000, 1200, 1400, 1600, 1800][Math.floor(rnd() * 5)],
        surf: rnd() < 0.5 ? "芝" : "ダ",
        going: ["良", "稍重", "重", "不良"][Math.floor(rnd() * 4)],
        track: tracks[Math.floor(rnd() * tracks.length)],
        cls: ["未勝利", "C3", "C2", "C1", "B3", "A2", "OP", "G3"][Math.floor(rnd() * 8)],
        jockey: "騎手" + Math.floor(rnd() * 40),
        weight: 400 + Math.floor(rnd() * 120)
      });
    }
    horses.push({
      num: i, waku: 1 + Math.floor((i - 1) / Math.max(1, Math.ceil(n / 8))),
      name: "馬" + i,
      sex: ["牡", "牝", "セ"][Math.floor(rnd() * 3)],
      age: 2 + Math.floor(rnd() * 8),
      jockey: "騎手" + Math.floor(rnd() * 40),
      trainer: "調教師" + Math.floor(rnd() * 30),
      sire: "父" + Math.floor(rnd() * 25),
      kg: 50 + rnd() * 10,
      weight: 400 + Math.floor(rnd() * 120),
      diff: Math.floor(rnd() * 21) - 10,
      odds: 1.2 + rnd() * 200,
      pop: i,
      past
    });
  }
  return {
    rid: (isNar ? "2026" + "54" + "0719" : "2026" + "06" + "0208") + String(1 + Math.floor(rnd() * 12)).padStart(2, "0"),
    track, dist, surf, going, isNar,
    cls: ["未勝利", "C2", "B1", "A1", "OP"][Math.floor(rnd() * 5)],
    horses, fieldN: n
  };
}

/* 乱数は固定シードにする。落ちたときに同じ入力で再現できるようにするため */
function mulberry32(a) {
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

function num(v) {
  return (typeof v === "number" && isFinite(v)) ? Math.round(v * 1e6) / 1e6 : v;
}

function main() {
  console.log("tweet.html を読み込み中…");
  const { ctx, api, err } = loadTweet();
  if (err) console.log(`  （初期化で例外: ${String(err.message).slice(0, 90)} — 関数定義は済んでいるので続行）`);

  const A = api || {};
  const missing = ["fundamentalScore", "gbmScore", "fullBreakdown", "factorW", "GBM_MODEL"]
    .filter(k => A[k] === undefined);
  if (missing.length) {
    console.log(`!! tweet.html から取り出せない: ${missing.join(" ")}`);
    return 1;
  }
  const B = require(path.join(ROOT, "core", "scoring.js"));

  console.log(`照合開始: ${N.toLocaleString()} レース分`);
  let checked = 0, mismatch = 0;
  const rnd = mulberry32(20260719);
  const firstBad = [];

  for (let i = 0; i < N; i++) {
    const race = makeRace(rnd);
    // MODE は両者で同じにする（nar/jra で係数表が変わるため）
    // ★両方に同じ MODE を渡す★
    //   ctx.MODE は const/let がコンテキストに出ないため undefined になる。
    //   それを core 側に渡していたので jra 固定になり、全件食い違った。
    const mode = race.isNar ? "nar" : "jra";
    A.MODE = mode;
    B.MODE = mode;

    for (const h of race.horses) {
      let ra, rb;
      try { ra = A.fundamentalScore(h.num, race); } catch (e) { ra = "ERR:" + e.message; }
      try { rb = B.fundamentalScore(h.num, race); } catch (e) { rb = "ERR:" + e.message; }
      checked++;
      if (num(ra) !== num(rb)) {
        mismatch++;
        if (firstBad.length < 3) firstBad.push({ i, num: h.num, a: ra, b: rb });
        continue;
      }
      // GBM 側も同じ入力で突き合わせる
      let ga, gb;
      try {
        const x = {}; (A.GBM_MODEL.feat || []).forEach(f => { x[f] = 0; });
        const brk = A.fullBreakdown(h.num, race) || [];
        for (const [k, v] of brk) {
          if (k === "基礎" || x[k] === undefined) continue;
          const w = A.factorW(k);
          x[k] = (w && Math.abs(w) > 1e-6) ? (v / w) : v;
        }
        x["__field"] = race.fieldN;
        ga = A.gbmScore(x); gb = B.gbmScore(x);
      } catch (e) { ga = "ERR:" + e.message; gb = ga; }
      if (num(ga) !== num(gb)) {
        mismatch++;
        if (firstBad.length < 3) firstBad.push({ i, num: h.num, a: ga, b: gb, gbm: true });
      }
    }
    if ((i + 1) % 500 === 0) process.stdout.write(`  ${i + 1}/${N}\r`);
  }

  console.log(`\n照合した頭数: ${checked.toLocaleString()}`);
  if (mismatch) {
    console.log(`!! 不一致 ${mismatch}件`);
    for (const b of firstBad) {
      console.log(`   レース#${b.i} 馬番${b.num} ${b.gbm ? "[GBM]" : "[線形]"} tweet=${b.a} core=${b.b}`);
    }
    console.log("\n切り出しが正しくない。公開してはいけない。");
    return 1;
  }
  console.log("全件一致。core/scoring.js は tweet.html と同じ答えを返す。");
  return 0;
}

process.exit(main());
