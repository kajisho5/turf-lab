/* 共通の道具。PHP の挙動（empty/isset/文字列化/date('c')）を写す関数もここに置く。 */

export interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  SEED_TOKEN: string;          // proxy_seed.php の t= （PHPと同じ値）
  ADMIN_TOKEN?: string;        // 移行・バックアップ用の管理口（secret）
  LINE_CHANNEL_TOKEN?: string; // line_push.php（secret。無ければドライラン扱い）
  SUBREQ_BUDGET?: string;      // 1回で外へ投げる上限（無料=45 / 有料=900）
}

/** どのサイトとして答えるか */
export type SiteId = 'k' | 'odds' | 'lab';
export interface Ctx {
  env: Env;
  req: Request;
  url: URL;
  site: SiteId;
  /** サイト内の相対パス（/odds/tweet.html → /tweet.html） */
  rel: string;
  exec: ExecutionContext;
}

export const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};
export const JSON_CT = 'application/json; charset=utf-8';
export const NO_STORE = 'no-store, no-cache, must-revalidate';

export function resp(body: BodyInit | null, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(body, { status, headers });
}
export function json(obj: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(phpJson(obj), { status, headers: { 'Content-Type': JSON_CT, ...headers } });
}

/** PHP json_encode と同じく、空の連想配列は [] で出す（{} を出すと PHP 時代と形が変わる所だけ使う） */
export function phpJson(obj: unknown): string {
  return JSON.stringify(obj);
}

/* ---------- PHP の真偽・型変換 ---------- */
export function isset(v: unknown): boolean { return v !== undefined && v !== null; }
export function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}
/** PHP の empty()。json_decode(...,true) では {} も [] になるので空オブジェクトも空扱い */
export function empty(v: unknown): boolean {
  if (v === undefined || v === null || v === false || v === 0 || v === '' || v === '0') return true;
  if (Array.isArray(v)) return v.length === 0;
  if (isObj(v)) return Object.keys(v).length === 0;
  if (typeof v === 'number' && Number.isNaN(v)) return false;
  return false;
}
/** PHP の (string) */
export function phpStr(v: unknown): string {
  if (v === undefined || v === null || v === false) return '';
  if (v === true) return '1';
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return String(v);
    // PHP8 は 1.5→"1.5"、1e20→"1.0E+20"。実用上は小数しか来ない
    return String(v);
  }
  if (typeof v === 'string') return v;
  return 'Array';
}
/** PHP の (int) */
export function phpInt(v: unknown): number {
  if (typeof v === 'number') return Number.isFinite(v) ? Math.trunc(v) : 0;
  if (typeof v === 'boolean') return v ? 1 : 0;
  if (typeof v === 'string') {
    const m = v.trim().match(/^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?/);
    return m ? Math.trunc(Number(m[0])) : 0;
  }
  return 0;
}
/** PHP の is_numeric */
export function isNumeric(v: unknown): boolean {
  if (typeof v === 'number') return Number.isFinite(v);
  if (typeof v !== 'string') return false;
  return /^\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*$/.test(v);
}
/** PHP の count()（配列でも連想配列でも数える） */
export function phpCount(v: unknown): number {
  if (Array.isArray(v)) return v.length;
  if (isObj(v)) return Object.keys(v).length;
  return v === undefined || v === null ? 0 : 1;
}
/** foreach で回せる中身 */
export function phpValues(v: unknown): unknown[] {
  if (Array.isArray(v)) return v;
  if (isObj(v)) return Object.values(v);
  return [];
}
/** PHP の is_array（リストも連想配列も真） */
export function isArr(v: unknown): boolean { return Array.isArray(v) || isObj(v); }

/** rec_path() と同じ置換 */
export function safeKey(s: string): string { return s.replace(/[^A-Za-z0-9_\-]/g, '_'); }

/** json_decode($raw, true)。失敗は null */
export async function readJson(req: Request, maxBytes = 0): Promise<unknown> {
  let t: string;
  try {
    if (maxBytes > 0) {
      const b = new Uint8Array(await req.arrayBuffer());
      t = new TextDecoder().decode(b.subarray(0, maxBytes));
    } else {
      t = await req.text();
    }
  } catch { return null; }
  try { return JSON.parse(t); } catch { return null; }
}

/** $_GET[name]（無ければ undefined） */
export function q(url: URL, name: string): string | undefined {
  const v = url.searchParams.get(name);
  return v === null ? undefined : v;
}

/* ---------- 時刻（サーバーはJST） ---------- */
const pad = (n: number, w = 2) => String(n).padStart(w, '0');
export function jst(ms = Date.now()): Date { return new Date(ms + 9 * 3600e3); }
/** date('c') → 2026-10-29T18:00:00+09:00 */
export function dateC(ms = Date.now()): string {
  const d = jst(ms);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}+09:00`;
}
/** date('Ymd') */
export function ymd(ms = Date.now()): string {
  const d = jst(ms);
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;
}
/** date('H:i:s') */
export function his(ms = Date.now()): string {
  const d = jst(ms);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}
export function nowSec(): number { return Math.floor(Date.now() / 1000); }

/* ---------- 文字列 ---------- */
export function htmlEsc(s: unknown): string {
  return phpStr(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
/** strip_tags の簡易版（タグとコメントを除く） */
export function stripTags(s: string): string {
  return s.replace(/<!--[\s\S]*?-->/g, '').replace(/<\/?[a-zA-Z!?][^>]*>/g, '').replace(/<[^>]*$/, '');
}
/** html_entity_decode(ENT_QUOTES, UTF-8) */
export function entityDecode(s: string): string {
  const named: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', '#039': "'", yen: '¥', copy: '©', times: '×' };
  return s.replace(/&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z0-9]+);/g, (m, e: string) => {
    if (e[0] === '#') {
      const n = e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      try { return String.fromCodePoint(n); } catch { return m; }
    }
    return named[e] ?? m;
  });
}
/** mb_substr($s, 0, n) */
export function mbSub(s: string, n: number): string { return Array.from(s).slice(0, n).join(''); }
export function mbLen(s: string): number { return Array.from(s).length; }

/* ---------- ハッシュ ---------- */
async function digestHex(alg: string, data: string | Uint8Array): Promise<string> {
  const buf = typeof data === 'string' ? new TextEncoder().encode(data) : data;
  const h = await crypto.subtle.digest(alg, buf);
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
export const sha1 = (s: string | Uint8Array) => digestHex('SHA-1', s);
export const sha256 = (s: string | Uint8Array) => digestHex('SHA-256', s);
export const md5 = (s: string | Uint8Array) => digestHex('MD5', s);

/* ---------- gzip（D1の2MB上限を超える本文用） ---------- */
export async function gzip(s: string): Promise<Uint8Array> {
  const cs = new CompressionStream('gzip');
  const w = new Blob([s]).stream().pipeThrough(cs);
  return new Uint8Array(await new Response(w).arrayBuffer());
}
export async function gunzip(b: ArrayBuffer | Uint8Array): Promise<string> {
  const ds = new DecompressionStream('gzip');
  const w = new Blob([b]).stream().pipeThrough(ds);
  return await new Response(w).text();
}
/** 1行に入れる本文。大きすぎれば gzip 側へ */
export const BIG = 1_800_000;
export async function packBody(s: string): Promise<{ body: string | null; gz: ArrayBuffer | null }> {
  if (new TextEncoder().encode(s).length < BIG) return { body: s, gz: null };
  return { body: null, gz: toAB(await gzip(s)) };
}
/** D1 に BLOB として渡す形 */
export function toAB(u: Uint8Array): ArrayBuffer {
  return u.buffer.slice(u.byteOffset, u.byteOffset + u.byteLength) as ArrayBuffer;
}
export async function unpackBody(row: { body?: unknown; body_gz?: unknown }): Promise<string> {
  if (typeof row.body === 'string') return row.body;
  if (row.body_gz) return gunzip(row.body_gz as ArrayBuffer);
  return '';
}

/* ---------- 外部取得の上限（無料プランは1回50本まで） ---------- */
export class Budget {
  left: number;
  constructor(env: Env, fallback = 45) { this.left = Number(env.SUBREQ_BUDGET || fallback) || fallback; }
  take(n = 1): boolean { if (this.left < n) return false; this.left -= n; return true; }
}

/** D1 の IN 句は100変数まで。分割して回す */
export function chunks<T>(a: T[], n: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < a.length; i += n) out.push(a.slice(i, i + n));
  return out;
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** 本文を文字列でつないで流す（数十MBの一覧を一度にメモリへ載せない） */
export function streamJson(headers: Record<string, string>, producer: (write: (s: string) => Promise<void>) => Promise<void>): Response {
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const w = writable.getWriter();
  const enc = new TextEncoder();
  (async () => {
    try { await producer((s) => w.write(enc.encode(s))); }
    catch (e) { console.error('stream error', e); }
    finally { try { await w.close(); } catch { /* noop */ } }
  })();
  return new Response(readable, { status: 200, headers });
}
