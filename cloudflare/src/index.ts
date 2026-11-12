/* kajikeiba-turf: 3サイト（kajikeiba.com / seventh-well.com/odds / seventh-well.com/lab）を1つのWorkerで出す。
 * URLとHTML/JSは旧サーバーと同じ。PHPのURLも同じ名前でここが答える。
 * 振り分けは下の表（ROUTES）1枚。Hono等のルーターは使わない（URLがPHPのファイル名そのもののため）。 */
import { Ctx, Env, SiteId, resp, json } from './lib';
import { predictions } from './api/predictions';
import { kaiko, results, horse, jockey, bias } from './api/data';
import { oddslog, oddsLogOld } from './api/oddslog';
import { proxy, proxySeed } from './api/proxy';
import { errorLog, errlogView, stats, statsView, linePush, cleanup, unzipGone } from './api/misc';
import { nardata, narOfficial } from './api/nar';
import { racePage, sitemap } from './api/race';
import { admin } from './admin';
import { scheduled } from './cron';
import { LAB_SUBS, LAB_PATH, LAB_ADSENSE } from './gen/meta';

type H = (c: Ctx) => Promise<Response>;

/* サイトごとに置いてあったPHP（deploy.py の PHP_MAP / PUBLIC_MAP と同じ並び） */
const ODDS: Record<string, H> = {
  '/proxy.php': proxy, '/proxy_seed.php': proxySeed, '/predictions.php': predictions, '/nardata.php': nardata,
  '/cleanup.php': cleanup, '/results.php': results, '/horse.php': horse, '/jockey.php': jockey, '/bias.php': bias,
  '/oddslog.php': oddslog, '/unzip.php': unzipGone, '/unzip_horse.php': unzipGone, '/error_log.php': errorLog,
  '/errlog_view.php': errlogView, '/line_push.php': linePush, '/kaiko.php': kaiko, '/odds-log.php': oddsLogOld,
  '/odds-cron.php': async (c) => {
    const r = await c.env.DB.prepare("SELECT v FROM kv WHERE k='odds_cron_state'").first<{ v: string }>();
    return resp(r?.v ?? '{}', 200, { 'Content-Type': 'application/json; charset=utf-8' });
  },
};
const PUBLIC: Record<string, H> = {
  '/proxy.php': proxy, '/proxy_seed.php': proxySeed, '/nar_official.php': narOfficial,
  '/race.php': (c) => racePage(c, c.url.searchParams.get('id')),
  '/sitemap.php': sitemap, '/sitemap.xml': sitemap,
  '/sitemap_urls.php': async () => resp('', 200, { 'Content-Type': 'text/html; charset=UTF-8' }),
  '/stats.php': stats, '/stats_view.php': statsView, '/error_log.php': errorLog, '/errlog_view.php': errlogView,
};

/* ---------- Apache の .htaccess 相当 ---------- */
const BOT_RE = /(GPTBot|ChatGPT-User|OAI-SearchBot|ClaudeBot|Claude-Web|anthropic-ai|CCBot|PerplexityBot|Bytespider|Amazonbot|meta-externalagent|FacebookBot|cohere-ai|Diffbot|omgili|ImagesiftBot|Scrapy|python-requests|node-fetch|Go-http-client|curl|wget)/i;
const HOTLINK_RE = /^\/(db\/(horses_search\.json|h\/|j\/)|db\/jra\/(horses_search\.json|h\/)|data\/(horses|jra_horses)\.json)/;
const APACHE_403 = '<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">\n<html><head>\n<title>403 Forbidden</title>\n</head><body>\n<h1>Forbidden</h1>\n<p>You don\'t have permission to access this resource.</p>\n</body></html>\n';
const APACHE_404 = '<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">\n<html><head>\n<title>404 Not Found</title>\n</head><body>\n<h1>Not Found</h1>\n<p>The requested URL was not found on this server.</p>\n</body></html>\n';
const forbidden = () => resp(APACHE_403, 403, { 'Content-Type': 'text/html; charset=iso-8859-1' });
const notFound = () => resp(APACHE_404, 404, { 'Content-Type': 'text/html; charset=iso-8859-1' });

/** deploy.py の lab_transform を出力側にかける（race.php 等の動的HTML用） */
export function labTransform(s: string): string {
  s = s.replace(new RegExp(LAB_ADSENSE, 'g'), '');
  for (const [a, b] of LAB_SUBS) s = s.split(a).join(b);
  for (const [pat, flags, rep] of LAB_PATH) s = s.replace(new RegExp(pat, flags.includes('g') ? flags : flags + 'g'), rep);
  return s.split('/lab/lab/').join('/lab/');
}

interface Where { site: SiteId; rel: string; base: string }
function resolve(url: URL): Where | Response | 'pass' {
  const host = url.hostname.toLowerCase();
  const p = url.pathname;
  const sub = (prefix: string): Where | Response | null => {
    if (p === prefix) return resp(null, 301, { Location: `${url.origin}${prefix}/${url.search}` });
    if (p.startsWith(prefix + '/')) return { site: prefix.slice(1) as SiteId, rel: p.slice(prefix.length), base: prefix };
    return null;
  };
  if (host === 'kajikeiba.com' || host === 'www.kajikeiba.com') {
    if (/^\/(odds|lab)(\/|$)/.test(p)) return notFound();      // 運営用を公開側に出さない
    return { site: 'k', rel: p, base: '' };
  }
  if (host === 'seventh-well.com' || host === 'www.seventh-well.com') {
    return sub('/odds') ?? sub('/lab') ?? 'pass';
  }
  // *.workers.dev・localhost（検証用）: /odds・/lab はそのまま、それ以外は公開サイト
  return sub('/odds') ?? sub('/lab') ?? { site: 'k', rel: p, base: '' };
}

async function serveStatic(c: Ctx, base: string): Promise<Response> {
  const { env, req, url } = c;
  const root = c.site === 'k' ? '/k' : `/s/${c.site}`;
  let rel = c.rel;
  try { rel = decodeURIComponent(rel); } catch { return notFound(); }
  if (rel.includes('..')) return notFound();
  const tryAsset = async (r: string) => {
    const u = new URL(url.toString());
    u.pathname = root + r; u.search = '';
    return env.ASSETS.fetch(new Request(u.toString(), { method: req.method === 'HEAD' ? 'HEAD' : 'GET', headers: req.headers }));
  };
  let r = await tryAsset(rel.endsWith('/') ? rel + 'index.html' : rel);
  if (r.status === 404 && !rel.endsWith('/') && !/\.[A-Za-z0-9]+$/.test(rel)) {
    const d = await tryAsset(rel + '/index.html');
    if (d.status === 200 || d.status === 304) return resp(null, 301, { Location: `${url.origin}${base}${c.rel}/${url.search}` });
  }
  if (r.status === 404) return notFound();
  const h = new Headers(r.headers);
  h.set('X-Content-Type-Options', 'nosniff');
  return new Response(r.body, { status: r.status, headers: h });
}

async function handle(req: Request, env: Env, exec: ExecutionContext): Promise<Response> {
  const url = new URL(req.url);
  if (url.protocol === 'http:' && !['localhost', '127.0.0.1'].includes(url.hostname)) {
    url.protocol = 'https:';
    return resp(null, 301, { Location: url.toString() });
  }
  if (url.pathname.startsWith('/__admin/')) return admin(req, env, url);

  const w = resolve(url);
  if (w === 'pass') return fetch(req);           // seventh-well.com の他のページは会社サイトへ
  if (w instanceof Response) return w;
  const c: Ctx = { env, req, url, site: w.site, rel: w.rel, exec };

  if (w.site !== 'odds') {
    if (BOT_RE.test(req.headers.get('user-agent') ?? '')) return forbidden();
    if (w.rel.startsWith('/cache/')) return notFound();
    if (HOTLINK_RE.test(w.rel)) {
      const ref = req.headers.get('referer') ?? '';
      const own = w.site === 'lab' ? /^https?:\/\/(www\.)?seventh-well\.com\/lab/i : /^https?:\/\/(www\.)?kajikeiba\.com/i;
      if (ref !== '' && !own.test(ref) && !ref.startsWith(url.origin + w.base + '/')) return forbidden();
    }
    const m = w.rel.match(/^\/race\/([0-9]{12})\/?$/);
    if (m) return finish(c, await racePage(c, m[1]));
  }

  const table = w.site === 'odds' ? ODDS : PUBLIC;
  const h = table[w.rel];
  if (h) return finish(c, await h(c));
  if (w.rel.endsWith('.php')) return notFound();
  return serveStatic(c, w.base);
}

/** lab では HTML/XML を lab 向けに書き換える（PHPファイル自体が書き換えて置かれていたのと同じ結果） */
async function finish(c: Ctx, r: Response): Promise<Response> {
  if (c.site !== 'lab') return r;
  const ct = r.headers.get('content-type') ?? '';
  if (!/text\/html|xml/.test(ct)) return r;
  const body = labTransform(await r.text());
  const h = new Headers(r.headers);
  h.delete('content-length');
  return new Response(body, { status: r.status, headers: h });
}

export default {
  async fetch(req: Request, env: Env, exec: ExecutionContext): Promise<Response> {
    try { return await handle(req, env, exec); }
    catch (e) {
      console.error('fatal', e);
      return json({ error: 'internal error' }, 500);
    }
  },
  scheduled: async (ev: ScheduledController, env: Env, exec: ExecutionContext) => { exec.waitUntil(scheduled(ev, env)); },
} satisfies ExportedHandler<Env>;
