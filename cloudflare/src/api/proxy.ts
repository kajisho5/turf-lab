/* proxy.php / proxy_seed.php の置き換え（netkeiba取得の自前プロキシ）
 *  ① キャッシュが90秒以内ならそれを返す（連打の負荷軽減）
 *  ② 直接取得（200〜399 かつ 200バイト超で成功）
 *  ③ r.jina.ai 中継（html → 小さければ markdown）。劣化上書きガードつき
 *  ④ 6時間以内の古いキャッシュ（結果ページは対象外）
 */
import { Ctx, Env, resp, json, q, sha1, nowSec, readJson, toAB } from '../lib';

const TTL_FRESH = 90;
const TTL_STALE = 21600;
const WL = /^https:\/\/[a-z0-9.-]*\.(netkeiba|keeeeeeba)\.com\//i;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

interface Cached { code: number; ctype: string; body: Uint8Array; age: number }

export async function cacheRead(env: Env, url: string): Promise<Cached | null> {
  const r = await env.DB.prepare('SELECT code, ctype, body, at FROM proxy_cache WHERE k=?').bind(await sha1(url)).first<{ code: number; ctype: string; body: ArrayBuffer; at: number }>();
  if (!r || !r.body) return null;
  const body = new Uint8Array(r.body as ArrayBuffer);
  if (body.length === 0) return null;
  return { code: r.code, ctype: r.ctype, body, age: nowSec() - r.at };
}
export async function cacheWrite(env: Env, url: string, code: number, ctype: string, body: Uint8Array): Promise<void> {
  if (body.length > 1_900_000) return;       // D1の1行上限。netkeibaのページは数十KBなので通常は来ない
  try {
    await env.DB.prepare('INSERT OR REPLACE INTO proxy_cache(k,code,ctype,body,at) VALUES(?,?,?,?,?)')
      .bind(await sha1(url), code, ctype, toAB(body), nowSec()).run();
  } catch (e) { console.error('proxy cache write', e); }
}

function b64urlDecode(u: string): string | null {
  let b = u.replace(/-/g, '+').replace(/_/g, '/');
  const pad = b.length % 4;
  if (pad) b += '='.repeat(4 - pad);
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(b)) return null;
  try {
    const bin = atob(b);
    // base64_decode は生バイト。URLとして使うので UTF-8 として読む
    return new TextDecoder().decode(Uint8Array.from(bin, (ch) => ch.charCodeAt(0)));
  } catch { return null; }
}

/** 直接取得。netkeibaの1回分 */
export async function directFetch(url: string, timeoutMs = 20000): Promise<{ ok: boolean; code: number; ctype: string; body: Uint8Array | null }> {
  try {
    const r = await fetch(url, {
      headers: { 'User-Agent': UA, Accept: 'text/html,application/xhtml+xml,*/*', 'Accept-Language': 'ja,en;q=0.8', Referer: 'https://nar.netkeiba.com/' },
      redirect: 'follow', signal: AbortSignal.timeout(timeoutMs),
    });
    const body = new Uint8Array(await r.arrayBuffer());
    const code = r.status;
    const ctype = r.headers.get('content-type') ?? '';
    return { ok: code >= 200 && code < 400 && body.length > 200, code, ctype, body };
  } catch {
    return { ok: false, code: 0, ctype: '', body: null };
  }
}

async function jina(url: string, htmlMode: boolean): Promise<{ b: string | null; c: number }> {
  const h: Record<string, string> = { Accept: 'text/html,application/json,*/*', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' };
  if (htmlMode) h['X-Return-Format'] = 'html';
  try {
    const r = await fetch('https://r.jina.ai/' + url, { headers: h, signal: AbortSignal.timeout(30000) });
    return { b: await r.text(), c: r.status };
  } catch { return { b: null, c: 0 }; }
}

/** proxy.php 本体。他のモジュール（race.php相当など）からも使えるよう、結果だけ返す版 */
export async function proxyGet(env: Env, url: string, diag = false): Promise<Response> {
  const base = { 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' };
  const volatile = /\/race\/result\.html/.test(url);
  const cached = await cacheRead(env, url);

  if (cached && cached.age < TTL_FRESH && cached.code >= 200 && cached.code < 400) {
    const h: Record<string, string> = { ...base, 'X-Proxy-Cache': 'fresh' };
    if (cached.ctype) h['Content-Type'] = cached.ctype;
    return resp(cached.body, cached.code, h);
  }

  const d = await directFetch(url);
  const h0: Record<string, string> = { ...base };
  if (d.ctype) h0['Content-Type'] = d.ctype;
  if (d.ok && d.body) {
    await cacheWrite(env, url, d.code, d.ctype, d.body);
    return resp(d.body, d.code, { ...h0, 'X-Proxy-Cache': 'miss' });
  }

  // ② 中継（r.jina.ai）
  let { b: jbody, c: jcode } = await jina(url, true);
  if (!(jbody !== null && jcode === 200 && jbody.length > 1000)) {
    const j2 = await jina(url, false);
    if (j2.b !== null && j2.c === 200 && j2.b.length > (jbody ?? '').length) { jbody = j2.b; jcode = j2.c; }
  }
  if (diag) {
    return resp(JSON.stringify({
      direct_code: d.code, direct_len: d.body ? d.body.length : -1, jina_code: jcode, jina_len: jbody !== null ? jbody.length : -1,
      jina_err: jbody === null ? 'curl_false' : jbody.slice(0, 120),
    }), 200, { ...h0, 'Content-Type': 'application/json' });
  }
  if (jbody !== null && jcode === 200 && jbody.length > 200) {
    let m = jbody.match(/^<html><head><\/head><body>([\s\S]*)<\/body><\/html>\s*$/);
    if (m) jbody = m[1];
    m = jbody.match(/^Title:[\s\S]*?Markdown Content:\s*\n([\s\S]*)$/);
    if (m) { const inner = m[1].trim(); if (inner !== '' && (inner[0] === '{' || inner[0] === '[')) jbody = inner; }
    const lt = jbody.replace(/^\s+/, '');
    const jct = lt !== '' && (lt[0] === '{' || lt[0] === '[') ? 'application/json; charset=UTF-8' : 'text/html; charset=UTF-8';
    const bytes = new TextEncoder().encode(jbody);
    // ★劣化上書きガード★ 既存より大幅に小さい中継結果で良いキャッシュを潰さない
    const worse = !!cached && bytes.length < cached.body.length * 0.6;
    if (!worse) await cacheWrite(env, url, 200, jct, bytes);
    else if (!volatile && cached!.age < TTL_STALE) {
      const h: Record<string, string> = { ...h0, 'X-Proxy-Cache': 'stale-kept' };
      if (cached!.ctype) h['Content-Type'] = cached!.ctype;
      return resp(cached!.body, 200, h);
    }
    return resp(bytes, 200, { ...h0, 'X-Proxy-Cache': 'relay', 'Content-Type': jct });
  }

  // ③ 古くてもキャッシュ（結果ページは除く）
  if (!volatile && cached && cached.age < TTL_STALE && cached.code >= 200 && cached.code < 400) {
    const h: Record<string, string> = { ...h0, 'X-Proxy-Cache': 'stale-fallback' };
    if (cached.ctype) h['Content-Type'] = cached.ctype;
    return resp(cached.body, 200, h);
  }
  if (!d.body || d.code === 0) return resp('fetch failed', 502, h0);
  return resp(d.body, d.code || 200, h0);
}

export async function proxy(c: Ctx): Promise<Response> {
  const { env, url } = c;
  let target = '';
  const u = q(url, 'u');
  if (u !== undefined && u !== '') { const d = b64urlDecode(u); if (d !== null) target = d; }
  else if (q(url, 'url') !== undefined) target = q(url, 'url')!;
  if (target === '' || !WL.test(target)) return resp('bad url', 400, { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'text/html; charset=UTF-8' });
  return proxyGet(env, target, q(url, 'diag') !== undefined);
}

export async function proxySeed(c: Ctx): Promise<Response> {
  const { env, req, url } = c;
  const H = { 'Content-Type': 'application/json; charset=UTF-8' };
  if ((q(url, 't') ?? '') !== env.SEED_TOKEN) return json({ ok: false, error: 'forbidden' }, 403, H);
  const r = (await readJson(req)) as Record<string, unknown> | null;
  const target = String(r?.url ?? '');
  const b64 = String(r?.body_b64 ?? '');
  const ctype = String(r?.ctype ?? 'text/html; charset=UTF-8');
  if (target === '' || !WL.test(target)) return json({ ok: false, error: 'bad url' }, 400, H);
  let body: Uint8Array | null = null;
  try { if (/^[A-Za-z0-9+/\s]*={0,2}\s*$/.test(b64)) body = Uint8Array.from(atob(b64.replace(/\s/g, '')), (ch) => ch.charCodeAt(0)); } catch { body = null; }
  if (!body || body.length < 200) return json({ ok: false, error: 'bad body' }, 400, H);
  await cacheWrite(env, target, 200, ctype, body);
  return json({ ok: true, file: (await sha1(target)) + '.cache', bytes: body.length }, 200, H);
}
