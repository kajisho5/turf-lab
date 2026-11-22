// 段階の確認（ゲート）と生成物の分け方の試験。通信しない。データは架空
import { gateFetch, gateGen, splitImages, joinImages, earlyFetchTime, running } from "../src/stages.js";
let ok = 0, ng = 0;
const eq = (n, a, b) => { const r = JSON.stringify(a) === JSON.stringify(b); r ? ok++ : (ng++, console.log("NG", n, JSON.stringify(a), JSON.stringify(b))); };
const IMG = "data:image/png;base64," + "Q".repeat(1500);
const tr = (tc, races) => ({ tc, trackName: "架空" + tc, races });
const R = (rid, o = {}) => ({ rid, no: 1, skip: false, pred: true, ...o });

// 朝
eq("朝: 全部そろえば ok", gateFetch("morning", { tracks: [{ tc: "01", total: 2, rids: ["a1", "a2"] }] }, [tr("01", [R("a1"), R("a2", { skip: true, pred: false })])]).s, "ok");
eq("朝: 見送りは欠けではない", gateFetch("morning", { tracks: [] }, [tr("01", [R("a1", { skip: true, pred: false })])]).s, "ok");
const m1 = gateFetch("morning", { tracks: [{ tc: "01", total: 2, rids: ["a1", "a2"] }] }, [tr("01", [R("a1")])]);
eq("朝: 保存の無いレース", [m1.s, m1.total, m1.got, m1.missing], ["miss", 2, 1, ["a2（保存なし）"]]);
eq("朝: 印の無いレース", gateFetch("morning", { tracks: [] }, [tr("01", [R("a1", { pred: false })])]).missing, ["a1（印なし）"]);
const m2 = gateFetch("morning", { tracks: [{ tc: "01", total: 1, rids: ["a1"] }] }, [tr("01", [R("a1")])], { expectRids: ["a1", "b1"] });
eq("朝: 一覧で拾ったレース（中央）が無い", [m2.s, m2.missing], ["miss", ["b1（保存なし）"]]);
eq("朝: レースの取れない場", gateFetch("morning", { tracks: [{ tc: "02", trackName: "架空2", total: 0, rids: [] }] }, [tr("01", [R("a1")])]).missing, ["架空2（レースが取れない）"]);
eq("朝: 読めない保存", gateFetch("morning", { tracks: [] }, [tr("01", [R("a1")]), { tc: "03", unreadable: 1, races: [] }]).missing, ["場03（保存を読めない）"]);
eq("朝: 何も無い日", gateFetch("morning", { tracks: [] }, []).s, "none");
// 夜
const res = new Set(["a1"]);
eq("夜: 結果がそろえば ok", gateFetch("evening", { tracks: [] }, [tr("01", [R("a1"), R("a2", { skip: true, pred: false })])], { results: res }).s, "ok");
const e1 = gateFetch("evening", { tracks: [] }, [tr("01", [R("a1"), R("a3")])], { results: res });
eq("夜: 結果の欠け", [e1.s, e1.got, e1.total, e1.missing, e1.why], ["miss", 1, 2, ["a3"], "結果が取れていないレースがある（1/2）"]);
eq("夜: 取消のレースは結果が無くてよい", gateFetch("evening", { tracks: [{ cancelledRids: ["a3"] }] }, [tr("01", [R("a1"), R("a3")])], { results: res }).s, "ok");
eq("夜: 印のレースが無い日", gateFetch("evening", { tracks: [] }, [tr("01", [R("a1", { skip: true, pred: false })])], { results: res }).s, "none");
// 生成
eq("生成(朝): ok", gateGen("morning", { ok: true, caption: "x", summary: { image: IMG }, cards: [{ image: IMG }, { image: IMG }] }, { expectCards: 2 }), { s: "ok", images: 3, posts: 1 });
eq("生成(朝): 枚数が合わない", gateGen("morning", { ok: true, caption: "x", cards: [{ image: IMG }] }, { expectCards: 2 }).s, "miss");
eq("生成(朝): 画像が空", gateGen("morning", { ok: true, caption: "x", cards: [{ tc: "01", image: "" }] }).why, "01 の画像が無い");
eq("生成(朝): 文が無い", gateGen("morning", { ok: true, cards: [{ image: IMG }] }).why, "投稿の文が無い");
eq("生成(夜): ok", gateGen("evening", { ok: true, posts: [{ text: "まとめ", images: [] }, { text: "", images: [IMG, IMG] }] }), { s: "ok", images: 2, posts: 2 });
eq("生成(夜): 画像0枚", gateGen("evening", { ok: true, posts: [{ text: "まとめ", images: [] }] }).s, "miss");
eq("生成: ページの失敗", gateGen("evening", { ok: false, error: "no races（確定レースなし）" }), { s: "fail", why: "no races（確定レースなし）" });
// 画像の分け方
const out = { ok: true, caption: "c", summary: { image: IMG }, cards: [{ tc: "01", image: IMG + "1" }], posts: [{ text: "t", images: [IMG + "2"] }] };
const { meta, imgs } = splitImages(out);
eq("分ける: 画像は本体から抜ける", [imgs.length, JSON.stringify(meta).includes("data:image"), meta.cards[0].image], [3, false, { $img: 1 }]);
eq("戻す: 元どおり", joinImages(JSON.parse(JSON.stringify(meta)), imgs), out);
// 時刻
eq("先行取得の回", ["06:50", "07:00", "07:20", "07:40", "08:00", "08:10"].map(t => earlyFetchTime(Date.parse(`2026-11-14T${t}:00+09:00`))), [null, { last: false }, { last: false }, { last: false }, { last: true }, null]);
eq("動いている途中の印は15分で切れる", [running({ s: "run", at: 1000 }, 1000 + 60e3), running({ s: "run", at: 1000 }, 1000 + 16 * 60e3), running({ s: "ok", at: 1000 }, 1000)], [true, false, false]);
console.log("OK", ok, "NG", ng); process.exit(ng ? 1 : 0);
