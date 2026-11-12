/* 定期実行（お名前.com の cron の置き換え）
 *   毎5分 0-13時UTC（JST 9:00〜22:55）: odds-cron.php と同じ処理＋10分ごとに公式結果の収集
 *   17 * * * *                      : sitemap用レースID（今日）・キャッシュ掃除
 *   37 15 * * *（JST 0:37）          : 前日分のレースIDを確定・30日の穴埋め（1回14日まで）
 */
import { Env, Budget, dateC, ymd, jst, nowSec, sleep, isObj, empty } from './lib';
import { oldUpsert, OLD_MAX } from './api/oddslog';
import { narCollect } from './api/nar';
import { indexRaces } from './api/race';

const WINDOW_BEFORE = 30, WINDOW_AFTER = 8, RESULT_AFTER = 4, REQ_SLEEP = 700, MAX_RACES = 24, MAX_SNAPS = 60;
const TH = { drop: 22, rise: 28, vel: 8 };
const TH_NAR = { drop: 30, rise: 40, vel: 12 };
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36';
const JRA: Record<string, string> = { '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京', '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉' };
const NAR: Record<string, string> = { '30': '門別', '35': '盛岡', '36': '水沢', '42': '浦和', '43': '船橋', '44': '大井', '45': '川崎', '46': '金沢', '47': '笠松', '48': '名古屋', '50': '園田', '51': '姫路', '54': '高知', '55': '佐賀', '65': '帯広' };
const trackOf = (rid: string, mode: string) => { const c = rid.slice(4, 6); const m = mode === 'nar' ? NAR : JRA; return m[c] ?? (mode === 'nar' ? `NAR:${c}` : `場${c}`); };
const phpRound = (v: number, p = 0) => { const f = 10 ** p; return Math.sign(v) * Math.round(Math.abs(v) * f) / f; };

async function httpGet(b: Budget, url: string, referer = ''): Promise<string | null> {
  if (!b.take()) return null;
  try {
    const h: Record<string, string> = { 'User-Agent': UA };
    if (referer) h.Referer = referer;
    const r = await fetch(url, { headers: h, redirect: 'follow', signal: AbortSignal.timeout(12000) });
    if (r.status < 200 || r.status >= 400) return null;
    return await r.text();
  } catch { return null; }
}

interface RaceRow { race_id: string; mode: string; track: string; no: number; post: string | null; postMin?: number }
async function fetchRaceList(b: Budget, date: string, mode: string): Promise<RaceRow[]> {
  const base = mode === 'nar' ? 'https://nar.netkeiba.com' : 'https://race.netkeiba.com';
  const html = await httpGet(b, `${base}/top/race_list_sub.html?kaisai_date=${date}`);
  if (!html) return [];
  const out: RaceRow[] = []; const seen = new Set<string>();
  for (const m of html.matchAll(/shutuba\.html\?race_id=(\d{12})/g)) {
    const rid = m[1]; if (seen.has(rid)) continue; seen.add(rid);
    // PHPはバイト位置から900バイト。日本語が混ざるので文字数で同程度を見る
    const win = html.slice(m.index!, m.index! + 600);
    const t = win.match(/(\d{1,2}:\d{2})/);
    out.push({ race_id: rid, mode, track: trackOf(rid, mode), no: parseInt(rid.slice(10, 12), 10), post: t ? t[1] : null });
  }
  return out;
}
const postMin = (p: string | null) => { const m = p?.match(/(\d{1,2}):(\d{2})/); return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null; };

async function fetchWinOdds(b: Budget, rid: string, mode: string): Promise<Record<string, number> | null> {
  const base = mode === 'nar' ? 'https://nar.netkeiba.com' : 'https://race.netkeiba.com';
  const api = mode === 'nar' ? 'api/api_get_nar_odds.html' : 'api/api_get_jra_odds.html';
  const qs = mode === 'nar' ? `race_id=${rid}&type=1` : `race_id=${rid}&type=1&action=init`;
  const raw = await httpGet(b, `${base}/${api}?${qs}`, `${base}/odds/index.html?race_id=${rid}`);
  if (!raw) return null;
  let j: Record<string, any>;
  try { j = JSON.parse(raw); } catch { return null; }
  if (!j) return null;
  const win: Record<string, number> = {};
  if (!empty(j.ary_odds)) {
    for (const [k, v] of Object.entries(j.ary_odds as Record<string, any>)) { const o = parseFloat(v?.Odds); if (o > 0) win[String(parseInt(k, 10))] = o; }
  } else {
    let od: Record<string, any> | null = null;
    if (!empty(j.data?.odds?.['1'])) od = j.data.odds['1'];
    else if (!empty(j.odds?.data?.['1'])) od = j.odds.data['1'];
    if (od) for (const [k, v] of Object.entries(od)) { const o = parseFloat(Array.isArray(v) ? v[0] : v); if (o > 0) win[String(parseInt(k, 10))] = o; }
  }
  return Object.keys(win).length ? win : null;
}

async function fetchResult(b: Budget, rid: string, mode: string) {
  const base = mode === 'nar' ? 'https://nar.netkeiba.com' : 'https://race.netkeiba.com';
  const html = await httpGet(b, `${base}/race/result.html?race_id=${rid}`);
  if (!html) return null;
  const arr: { rank: number; waku: number | null; num: string; name: string; jockey: string; pop: number | null; time: string | null }[] = [];
  for (const m of html.matchAll(/<tr[\s\S]*?<\/tr>/g)) {
    const r = m[0];
    const rk = r.match(/class="Rank"[^>]*>\s*(\d{1,2})\s*</); if (!rk) continue;
    const nums = [...r.matchAll(/class="Num Waku\d*"[^>]*>\s*(?:<div[^>]*>)?\s*(\d{1,2})/g)].map((x) => x[1]);
    const waku = nums[0] !== undefined ? parseInt(nums[0], 10) : null;
    const num = nums[1] !== undefined ? String(parseInt(nums[1], 10)) : null;
    const n = r.match(/\/horse\/\d+[^"]*"[^>]*>([^<]{1,30})</);
    const jk = r.match(/\/jockey\/(?:result\/recent\/)?\d+[^"]*"[^>]*>\s*([^<]{1,16}?)\s*</);
    const p = r.match(/Odds_Ninki[^>]*>\s*(?:<span[^>]*>)?\s*(\d{1,2})/);
    const t = r.match(/(\d:\d{2}\.\d)/);
    if (!num) continue;
    arr.push({ rank: parseInt(rk[1], 10), waku, num, name: n ? n[1].trim() : '', jockey: jk ? jk[1].trim() : '', pop: p ? parseInt(p[1], 10) : null, time: t ? t[1] : null });
  }
  arr.sort((a, c) => a.rank - c.rank);
  return arr.length ? arr : null;
}

type Series = { ts: number; win: Record<string, number> }[];
function detect(series: Series, th: { drop: number; rise: number; vel: number }) {
  const first = series[0].win; const last = series[series.length - 1].win;
  const prev = series.length >= 2 ? series[series.length - 2].win : first;
  const picks: { num: string; score: number; tags: string[]; totalPct: number; recentPct: number; odds: number }[] = [];
  for (const [num, od] of Object.entries(last)) {
    if (!(num in first) || first[num] <= 0) continue;
    const total = (od - first[num]) / first[num] * 100;
    const recent = prev[num] !== undefined && prev[num] > 0 ? (od - prev[num]) / prev[num] * 100 : 0;
    const tags: string[] = [];
    if (total <= -th.drop) tags.push('🔻急落');
    let band = 1.02 * Math.exp(-Math.pow(Math.log(od / 3.5), 2) / 2.6) + 0.05; band = Math.min(1, band);
    if (total >= th.rise && band >= 0.35) tags.push('🔺急騰');
    if (Math.abs(recent) >= th.vel && band >= 0.3) tags.push('⚡直前急変');
    if (!tags.length) continue;
    const dir = total < 0 ? 1.0 : 0.45;
    const score = phpRound(Math.min(60, Math.abs(total)) / 60 * 60 * band * dir);
    picks.push({ num: String(num), score, tags, totalPct: phpRound(total, 1), recentPct: phpRound(recent, 1), odds: phpRound(od, 1) });
  }
  picks.sort((a, b) => b.score - a.score);
  return picks.slice(0, 5);
}

export async function oddsCron(env: Env): Promise<Record<string, unknown>> {
  const b = new Budget(env);
  const d = jst();
  const now = d.getUTCHours() * 60 + d.getUTCMinutes();
  const today = ymd();
  let races: RaceRow[] = [];
  for (const mode of ['jra', 'nar']) { races = races.concat(await fetchRaceList(b, today, mode)); await sleep(REQ_SLEEP); }
  let targets: RaceRow[] = [];
  for (const r of races) {
    const pm = postMin(r.post); if (pm === null) continue;
    if (pm - WINDOW_BEFORE <= now && now <= pm + WINDOW_AFTER) targets.push({ ...r, postMin: pm });
  }
  targets.sort((a, c) => a.postMin! - c.postMin!);
  targets = targets.slice(0, MAX_RACES);

  const row = await env.DB.prepare("SELECT v FROM kv WHERE k='odds_snaps'").first<{ v: string }>();
  let snaps: Record<string, any> = {};
  try { const j = row ? JSON.parse(row.v) : {}; if (isObj(j)) snaps = j; } catch { /* noop */ }
  let collected = 0, reconciled = 0;
  const touched = new Set<string>();

  for (const r of targets) {
    const rid = r.race_id; const mode = r.mode; const th = mode === 'nar' ? TH_NAR : TH;
    if (now <= r.postMin!) {
      const win = await fetchWinOdds(b, rid, mode); await sleep(REQ_SLEEP);
      if (win) {
        if (!snaps[rid]) snaps[rid] = { mode, track: r.track, no: r.no, postMin: r.postMin, series: [] };
        snaps[rid].series.push({ ts: nowSec(), win });
        if (snaps[rid].series.length > MAX_SNAPS) snaps[rid].series = snaps[rid].series.slice(-MAX_SNAPS);
        collected++;
        if (snaps[rid].series.length >= 2) {
          const picks = detect(snaps[rid].series, th);
          if (picks.length) {
            await oldUpsert(env, mode === 'nar' ? 'nar' : 'jra', [{ id: rid, mode, track: r.track, no: String(r.no), going: null, surface: null, dist: null, ts: nowSec() * 1000, picks, result: null }], false);
            touched.add(mode === 'nar' ? 'nar' : 'jra');
          }
        }
      }
    }
    if (now >= r.postMin! + RESULT_AFTER) {
      const lm = mode === 'nar' ? 'nar' : 'jra';
      const ex = await env.DB.prepare('SELECT body FROM oddslog_old WHERE mode=? AND id=?').bind(lm, rid).first<{ body: string }>();
      let rec: Record<string, any> | null = null;
      try { rec = ex ? JSON.parse(ex.body) : null; } catch { rec = null; }
      if (rec && empty(rec.result)) {
        const res = await fetchResult(b, rid, mode); await sleep(REQ_SLEEP);
        if (res) {
          const w = res.find((x) => x.rank === 1) ?? null;
          rec.result = { win: w ? w.num : null, place3: res.filter((x) => x.rank <= 3).map((x) => x.num), winWaku: w ? w.waku : null, winPop: w ? w.pop : null, winJockey: w ? w.jockey : null, winTime: w ? w.time : null, fetched: nowSec() * 1000 };
          await oldUpsert(env, lm, [rec], false);
          touched.add(lm);
          reconciled++;
          delete snaps[rid];
        }
      }
    }
  }
  for (const m of touched) await oldUpsert(env, m, [], true);
  // 発走から36時間以上たった収集中データは捨てる（PHP版は結果照合できないと残り続けていた）
  const cutoff = nowSec() - 36 * 3600;
  for (const [rid, s] of Object.entries(snaps)) {
    const last = s?.series?.[s.series.length - 1]?.ts ?? 0;
    if (last && last < cutoff) delete snaps[rid];
  }
  await env.DB.batch([
    env.DB.prepare("INSERT OR REPLACE INTO kv(k,v,at) VALUES('odds_snaps',?,?)").bind(JSON.stringify(snaps), nowSec()),
    env.DB.prepare("INSERT OR REPLACE INTO kv(k,v,at) VALUES('odds_cron_state',?,?)").bind(JSON.stringify({ lastRun: dateC(), now, targets: targets.length, collected, reconciled, budgetLeft: b.left }), nowSec()),
  ]);
  return { ok: true, targets: targets.length, collected, reconciled };
}

export async function scheduled(ev: ScheduledController, env: Env): Promise<void> {
  const cron = ev.cron;
  if (cron.startsWith('*/5')) {
    try { await oddsCron(env); } catch (e) { console.error('oddsCron', e); }
    const m = jst(ev.scheduledTime).getUTCMinutes();
    if (m % 10 === 0) { try { await narCollect(env); } catch (e) { console.error('narCollect', e); } }
    return;
  }
  if (cron.startsWith('17 ')) {
    try { await indexRaces(env, ymd(ev.scheduledTime)); } catch (e) { console.error('indexRaces', e); }
    const t = nowSec();
    await env.DB.batch([
      env.DB.prepare('DELETE FROM proxy_cache WHERE at < ?').bind(t - 3 * 86400),
      env.DB.prepare('DELETE FROM page_cache WHERE at < ?').bind(t - 3 * 86400),
    ]);
    return;
  }
  // 日次: 前日分の確定と、30日のうち抜けている日の穴埋め（1回最大14日＝外部28本）
  const days: string[] = [];
  for (let i = 1; i < 30; i++) days.push(ymd(ev.scheduledTime - i * 86400e3));
  const rs = await env.DB.prepare(`SELECT day, COUNT(*) AS n FROM race_index WHERE day >= ? GROUP BY day`).bind(days[days.length - 1]).all<{ day: string; n: number }>();
  const have = new Set(rs.results.map((r) => r.day));
  const todo = [days[0], ...days.slice(1).filter((d) => !have.has(d))].slice(0, 14);
  for (const d of todo) { try { await indexRaces(env, d); } catch (e) { console.error('indexRaces', d, e); } }
}

export { OLD_MAX };
