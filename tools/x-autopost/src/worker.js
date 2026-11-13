/* =====================================================================
   カジ競馬 X自動投稿  —  Cloudflare Worker
   ---------------------------------------------------------------------
   PC不要・窓なしで、毎日 X に自動投稿する。
     朝 8:00(JST) 予想:  各場の予想カード画像（4枚/ツイートで分割）
     夜 21:30(JST) 結果: ①的中まとめ ②回収率です＋画像2 ③段階別成績 ④答え合わせ

   仕組み:
     Browser Rendering でヘッドレスChromeを起動し、legacyの tweet.html を
       ?auto=morning|evening&mode=nar|jra で開く → ページが window.__autoOut に
       「投稿ぶんの text＋画像(dataURL)」を出す（tweet.html側に実装済み）。
     それを読み取り、X API(OAuth1.0a: 画像アップロード v1.1 + 投稿 v2)で
     スレッドとして投稿する。

   ★安全設計★
     - DRYRUN=1 の間は【投稿しない】。/run?...&dry=1 で内容(text/画像枚数)だけ確認できる。
     - 予想はオッズ前・公開後不変。狙い目は朝の保存信頼度基準（tweet.html側で担保）。
     - 秘密情報は Worker secret（X_*）。コードに鍵は書かない。

   ルート:
     GET /run?kind=morning|evening&key=<TRIGGER_KEY>[&dry=1][&mode=nar|jra]
         手動実行/テスト。dry=1 なら投稿せず要約JSONを返す。
     cron: 23:30 UTC=朝8:30 / 13:30 UTC=夜22:30（wrangler.toml）。朝/夜は動いた時刻で決める
   ===================================================================== */

import puppeteer from "@cloudflare/puppeteer";

import { toThread, mergePosts, MAX_MEDIA } from "./posts.js";
import { runHits, rememberMorning } from "./hits.js";
const MODES = ["nar", "jra"];               // 中央は開催が無ければ0件で自然にスキップ
/* ★2026-10-29★ Cloudflare上の初回ドライランで朝だけ500になった（夜は成功）。
   朝は全場予想（runAll）を回すので手元で90秒、Cloudflare上ではさらに長くかかり、待ち時間150秒を超えていた見込み
   （ダッシュボードの実行時間P90=249秒）。待ちを7分に延ばし、ブラウザが無操作で閉じないよう keep_alive を付け、
   途中で失敗しても500にせずモード単位のエラーとして返す（何が起きたかを結果に残す）。 */
const RENDER_TIMEOUT_MS = 420000;           // __autoOut 待ちの上限（朝の全場予想がCloudflare上で数分かかる）
const KEEP_ALIVE_MS = 600000;               // ブラウザを無操作で閉じない時間（既定60秒では足りない）

/** 動いた時刻（ミリ秒）から朝/夜を決める。日本時間の 4:00〜13:59 に動いたら朝の予想、それ以外は夜の結果 */
const MONTHLY_CRON = "0 0 1 * *";       // 月間まとめ（毎月1日 9:00 日本時間）。wrangler.toml の crons と同じ文字列
const HITS_CRON = "*/10 1-13 * * *";    // ★勝負の的中速報（日本時間 10:00〜22:50 の10分おき）。wrangler.toml の crons と同じ文字列
const KEYCHECK_CRON = "22 3 * * *";   // 鍵の確認用の臨時の時刻（UTC）。使う時だけ wrangler.toml の crons に足す

/** 動いた時刻（ミリ秒）の、日本時間で見た「前の月」を YYYYMM で返す */
export function prevMonth(ms) {
  const j = new Date((Number(ms) || Date.now()) + 9 * 3600 * 1000);
  const d = new Date(Date.UTC(j.getUTCFullYear(), j.getUTCMonth() - 1, 1));
  return `${d.getUTCFullYear()}${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function kindForTime(ms) {
  const h = new Date((Number(ms) || Date.now()) + 9 * 3600 * 1000).getUTCHours();
  return (h >= 4 && h < 14) ? "morning" : "evening";
}

export default {
  async scheduled(event, env, ctx) {
    // 動いた時刻（日本時間）で朝/夜を決める。cron の文字列には頼らない
    // （以前は "0 23 * * *" と完全一致した時だけ朝だったので、時刻をずらすと朝の回が夜扱いになった）
    // 鍵の確認だけ（投稿しない・画像も作らない）。wrangler.toml に KEYCHECK_CRON と同じ時刻を臨時で足した時だけ動く。
    // Xに「自分は誰か」を聞くだけで、結果（OK/NG とXの返答の番号）をメールで知らせる。鍵の値は出さない
    if (event.cron === KEYCHECK_CRON) {
      ctx.waitUntil((async () => {
        let line = "";
        try {
          const url = "https://api.twitter.com/2/users/me";
          const res = await fetch(url, { headers: { Authorization: await oauthHeader(env, "GET", url, {}) } });
          const body = (await res.text()).slice(0, 200);
          line = res.ok ? `OK（Xの返答 ${res.status}）: ${body}` : `NG（Xの返答 ${res.status}）: ${body}`;
        } catch (e) { line = "NG（通信の失敗）: " + String(e && e.message || e); }
        console.log("autopost keycheck", line);
        if (env.MAIL) await env.MAIL.send({
          to: "kajiyama@seventh-well.com",
          from: { email: "autopost@notify.seventh-well.com", name: "カジ競馬 自動投稿" },
          subject: `【鍵の確認】${line.startsWith("OK") ? "OK" : "NG"}`,
          text: "Xの鍵の確認（投稿はしていません）\n" + line + "\n",
        });
      })().catch(e => console.error("keycheck", e)));
      return;
    }
    // ★勝負の的中速報（10分おき）。朝・夜の回とは別の時刻の指定で動く
    if (event.cron === HITS_CRON) {
      if (env.HITS !== "1") return;
      ctx.waitUntil((async () => {
        try {
          const r = await runHits(env, (text, toId) => createTweet(env, text, [], toId), { dry: env.DRYRUN === "1" });
          if (r.checked || r.posted.length) console.log("autopost hits", JSON.stringify(r));
        } catch (e) { console.error("hits", String(e && e.message || e)); }
      })());
      return;
    }
    // 月間まとめ（毎月1日 9:00）。前の月の成績を1枚で出す
    if (event.cron === MONTHLY_CRON) {
      ctx.waitUntil((async () => {
        let r = null, err = null;
        try { r = await runMonthly(env, prevMonth(event.scheduledTime), { dry: env.DRYRUN === "1" }); console.log("autopost monthly", JSON.stringify(r)); }
        catch (e) { err = e; console.error("monthly", e); }
        try { await notifyMail(env, "monthly", r, err); } catch (e) { console.error("notify mail failed", String(e && e.message || e)); }
      })());
      return;
    }
    const kind = kindForTime(event.scheduledTime);
    ctx.waitUntil((async () => {
      let r = null, err = null;
      try { r = await runAll(env, kind, { dry: env.DRYRUN === "1" }); console.log("autopost result", JSON.stringify(r)); }
      catch (e) { err = e; console.error("scheduled", kind, e); }
      try { await notifyMail(env, kind, r, err); } catch (e) { console.error("notify mail failed", String(e && e.message || e), String(e && e.code || "")); }
    })());
  },

  async fetch(req, env) {
    const url = new URL(req.url);
    if (!url.pathname.endsWith("/run")) {
      return json({ ok: true, usage: "/run?kind=morning|evening&key=TRIGGER_KEY[&dry=1][&mode=nar|jra]" });
    }
    if (!env.TRIGGER_KEY || url.searchParams.get("key") !== env.TRIGGER_KEY) {
      return json({ error: "forbidden (key不一致)" }, 403);
    }
    const kind = url.searchParams.get("kind") === "evening" ? "evening" : "morning";
    const dry = url.searchParams.get("dry") === "1" || env.DRYRUN === "1";
    const only = url.searchParams.get("mode");           // テスト用: 片モードだけ
    try {
      const res = await runAll(env, kind, { dry, only });
      return json(res);
    } catch (e) {
      return json({ error: String(e && e.message || e), stack: String(e && e.stack || "") }, 500);
    }
  },
};

/* ---------- 結果メール（成功・失敗とも。2026-10-30 ユーザー指示） ----------
   送信: Cloudflare Email Service（送信元ドメイン notify.seventh-well.com は登録済み）。
   宛先は wrangler.toml の send_email の destination_address に固定（他へは送れない）。 */
async function notifyMail(env, kind, r, err) {
  if (!env.MAIL) return;
  const kindLbl = kind === "morning" ? "朝の予想" : kind === "monthly" ? "月間まとめ" : "夜の結果";
  const lines = [];
  let posted = 0, failed = 0;
  if (err) { failed++; lines.push(`全体エラー: ${String(err && err.message || err)}`); }
  for (const [mode, m] of Object.entries((r && r.modes) || {})) {
    const lbl = mode === "nar" ? "地方" : "中央";
    if (m.posted && m.posted.length) {
      posted += m.posted.length;
      lines.push(`■${lbl}: ${m.posted.length}件投稿`);
      m.posted.forEach((p, i) => lines.push(`  ${i + 1}. https://x.com/kaji_keiba/status/${p.id}（画像${p.images}枚）`));
      if (m.mergeError) lines.push(`  ※1件にまとめた投稿は通らなかったので、分けて投稿しました — ${String(m.mergeError).slice(0, 200)}`);
    } else if (m.error) {
      // 中央は平日に開催が無いので「レース無し」は失敗扱いにしない
      const noRace = /no races|レースがありません|0件|count":0/.test(String(m.error));
      if (!noRace) failed++;
      lines.push(`■${lbl}: ${noRace ? "開催なし" : "失敗"} — ${String(m.error).slice(0, 300)}`);
    } else {
      lines.push(`■${lbl}: 投稿なし（${(m.posts || []).length}件の素材）`);
    }
  }
  if (r && r.dry) lines.unshift("※お試しモード（Xには投稿していません）");
  const status = failed ? "⚠失敗あり" : (posted ? "投稿OK" : "投稿なし");
  const jst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(5, 16).replace("T", " ");
  await env.MAIL.send({
    to: "kajiyama@seventh-well.com",   // 必須（binding の destination_address と同じ1件）
    from: { email: "autopost@notify.seventh-well.com", name: "カジ競馬 自動投稿" },
    subject: `【${status}】${kindLbl} ${jst}`,
    text: lines.join("\n") + "\n\n記録: https://dash.cloudflare.com/78ef1242bb9514e7f6ccf32f9f94e744/workers/services/view/kajikeiba-autopost/production/observability/events\n",
  });
}

/* 朝/夜を全モード分まとめて実行。dry=true なら投稿せず要約を返す。 */
async function runAll(env, kind, { dry, only, date, caption } = {}) {
  const modes = only ? [only] : MODES;
  const browser = await puppeteer.launch(env.BROWSER, { keep_alive: KEEP_ALIVE_MS });
  const summary = { kind, dry: !!dry, at: new Date().toISOString(), modes: {} };
  try {
    for (const mode of modes) {
      const t0 = Date.now();
      try {
        const out = await renderOne(browser, env, kind, mode, date);
        const thread = out.ok ? toThread(kind, mode, out, caption) : [];
        const one = mergePosts(thread);          // 1件にまとめた形（まとめられない時は null）
        const posts = one ? [one] : thread;
        summary.modes[mode] = { ok: out.ok, error: out.error || null, sec: Math.round((Date.now() - t0) / 1000),
          posts: posts.map(p => ({ text: p.text, images: p.images.length })) };
        if (!dry && posts.length) {
          let r;
          try { r = await postThread(env, posts); }
          catch (e) {
            // 1件にまとめた投稿をXが受け付けなかった（画像の枚数・文の長さなど）→ 今までどおり分けて出す
            if (!one) throw e;
            summary.modes[mode].mergeError = String(e && e.message || e);
            console.error("merged post failed, falling back to thread", summary.modes[mode].mergeError);
            r = await postThread(env, thread);
          }
          summary.modes[mode].posted = r;
          // 朝の投稿のIDを覚えておく（的中速報をこの投稿への返信で出すため）。失敗しても投稿は成功のまま
          if (kind === "morning" && r && r[0] && r[0].id) {
            try { await rememberMorning(env, out.date, mode, r[0].id); } catch (e) { console.error("rememberMorning", String(e && e.message || e)); }
          }
        }
      } catch (e) {
        summary.modes[mode] = { ok: false, error: String(e && e.message || e), sec: Math.round((Date.now() - t0) / 1000) };
      }
    }
  } finally {
    try { await browser.close(); } catch (_) { /* 既に閉じていても結果は返す */ }
  }
  return summary;
}

/* 月間まとめ: tweet.html?auto=monthly&ym=YYYYMM を開いて画像1枚を投稿する。500レース未満の月は投稿しない（ページ側が断る） */
async function runMonthly(env, ym, { dry } = {}) {
  const browser = await puppeteer.launch(env.BROWSER, { keep_alive: KEEP_ALIVE_MS });
  const summary = { kind: "monthly", ym, dry: !!dry, at: new Date().toISOString(), modes: {} };
  try {
    const out = await renderOne(browser, env, "monthly", "nar", null, `&ym=${ym}`);
    const posts = (out.ok && out.image) ? [{ text: out.text || "", images: [out.image] }] : [];
    summary.modes.nar = { ok: out.ok, error: out.error || null, posts: posts.map(p => ({ text: p.text, images: p.images.length })) };
    if (!dry && posts.length) summary.modes.nar.posted = await postThread(env, posts);
  } finally {
    try { await browser.close(); } catch (_) { /* noop */ }
  }
  return summary;
}

/* tweet.html を1枚開いて window.__autoOut を回収 */
async function renderOne(browser, env, kind, mode, date, extra) {
  const page = await browser.newPage();
  try {
    const u = `${env.TWEET_URL}?auto=${kind}&mode=${mode}` + (date ? `&date=${date}` : "") + (extra || "");
    await page.goto(u, { waitUntil: "domcontentloaded", timeout: 90000 });
    const out = await page.waitForFunction(
      () => (window.__autoOut && (window.__autoOut.ok === true || window.__autoOut.ok === false)) ? window.__autoOut : null,
      { timeout: RENDER_TIMEOUT_MS, polling: 2000 }
    ).then(h => h.jsonValue());
    return out || { ok: false, error: "no __autoOut" };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  } finally {
    try { await page.close(); } catch (_) { /* noop */ }
  }
}

/* ---------- X 投稿（OAuth1.0a）。posts が1件なら1投稿、複数ならスレッド ----------
   2026-11-13: Xの画像上限が4→20枚になった（API の media_ids も最大20）。まず1件にまとめて出し、
   通らなければ runAll が今までどおり4枚ずつのスレッドで出し直す。 */
async function postThread(env, posts) {
  const done = [];
  let replyTo = null;
  for (const p of posts) {
    const mediaIds = [];
    for (const dataUrl of p.images.slice(0, MAX_MEDIA)) {
      const id = await uploadMedia(env, dataUrl);
      if (id) mediaIds.push(id);
    }
    const id = await createTweet(env, p.text, mediaIds, replyTo);
    replyTo = id;                       // 次を同スレッドにぶら下げる
    done.push({ id, images: mediaIds.length });
  }
  return done;
}

async function uploadMedia(env, dataUrl) {
  const b64 = dataUrl.split(",")[1];
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const url = "https://upload.twitter.com/1.1/media/upload.json";
  // media/upload は multipart。OAuth1.0aの署名は本文パラメータを含めない（oauth_* のみ）。
  const auth = await oauthHeader(env, "POST", url, {});
  const form = new FormData();
  form.append("media", new Blob([bin], { type: "image/png" }), "card.png");
  const res = await fetch(url, { method: "POST", headers: { Authorization: auth }, body: form });
  if (!res.ok) throw new Error(`media upload ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const j = await res.json();
  return j.media_id_string;
}

async function createTweet(env, text, mediaIds, replyTo) {
  const url = "https://api.twitter.com/2/tweets";
  const body = { text: text || "" };
  if (mediaIds && mediaIds.length) body.media = { media_ids: mediaIds };
  if (replyTo) body.reply = { in_reply_to_tweet_id: replyTo };
  // v2 は JSON本文。OAuth1.0a署名は本文JSONを含めない（oauth_* のみ）。
  const auth = await oauthHeader(env, "POST", url, {});
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: auth, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`tweet ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const j = await res.json();
  return j.data && j.data.id;
}

/* ---- OAuth1.0a 署名（HMAC-SHA1・Web Crypto） ---- */
function pe(s) { return encodeURIComponent(s).replace(/[!*'()]/g, c => "%" + c.charCodeAt(0).toString(16).toUpperCase()); }

async function oauthHeader(env0, method, url, extraParams) {
  // 鍵は前後の空白・改行を除いて使う（PowerShell から貼ると末尾に改行が付くことがある）
  const t = v => String(v == null ? "" : v).trim();
  const env = { X_API_KEY: t(env0.X_API_KEY), X_API_SECRET: t(env0.X_API_SECRET),
                X_ACCESS_TOKEN: t(env0.X_ACCESS_TOKEN), X_ACCESS_SECRET: t(env0.X_ACCESS_SECRET) };
  const oauth = {
    oauth_consumer_key: env.X_API_KEY,
    oauth_nonce: crypto.randomUUID().replace(/-/g, ""),
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: String(Math.floor(Date.now() / 1000)),
    oauth_token: env.X_ACCESS_TOKEN,
    oauth_version: "1.0",
  };
  const all = { ...oauth, ...(extraParams || {}) };
  const paramStr = Object.keys(all).sort().map(k => `${pe(k)}=${pe(all[k])}`).join("&");
  const base = [method.toUpperCase(), pe(url), pe(paramStr)].join("&");
  const signingKey = `${pe(env.X_API_SECRET)}&${pe(env.X_ACCESS_SECRET)}`;
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(signingKey),
    { name: "HMAC", hash: "SHA-1" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(base));
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)));
  oauth.oauth_signature = sigB64;
  return "OAuth " + Object.keys(oauth).sort().map(k => `${pe(k)}="${pe(oauth[k])}"`).join(", ");
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj, null, 1), {
    status, headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}
