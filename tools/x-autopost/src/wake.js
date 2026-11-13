/* 毎朝のデータ更新を起こす（2026-11-14）
   GitHub の予定実行（deploy-site の 2:40〜7:40）が2日続けて予定の時刻に動かなかったので、
   Cloudflare の時刻指定（4:40・5:40）から deploy-site を起こす。GitHub の予定実行は予備として残す。
   - 公開中の索引（nar_index_asof.json）の built が今日なら、もう更新済みなので何もしない。
   - 鍵（GH_DISPATCH_TOKEN）が登録されていなければ何もしない（値はここでは見ない・出さない）。
   - 起こすだけ。作り直しと公開は GitHub の側（deploy-site）がやる。 */
const REPO = "kajisho5/turf-lab", WORKFLOW = "deploy-site.yml";
const ASOF_URL = "https://seventh-well.com/odds/data/nar_index_asof.json";

/* 今日（日本時間）の YYYYMMDD */
export function jstDay(ms) { return new Date((Number(ms) || Date.now()) + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, ""); }

/* 起こす必要があるか。asof＝公開中の索引の情報（読めなかった時は null＝起こす） */
export function needWake(asof, today) { return !(asof && String(asof.built || "") === String(today)); }

export async function wakeDeploy(env, ms) {
  const today = jstDay(ms);
  if (!env.GH_DISPATCH_TOKEN) return { today, woke: false, why: "鍵（GH_DISPATCH_TOKEN）が登録されていない" };
  let asof = null;
  try { const r = await fetch(`${ASOF_URL}?_=${Date.now()}`, { headers: { Accept: "application/json" } }); if (r.ok) asof = await r.json(); } catch { asof = null; }
  if (!needWake(asof, today)) return { today, woke: false, why: "もう今日ぶんに更新済み", asof };
  const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "kajikeiba-autopost", "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main" }),
  });
  // 成功は 204（中身なし）。失敗の時は GitHub の返答の先頭だけ残す（鍵の値は返答に含まれない）
  const body = res.ok ? "" : (await res.text()).slice(0, 200);
  return { today, woke: res.ok, status: res.status, body, asof };
}

/* 鍵の期限まであと何日か（GitHub が返答の見出しに入れてくる期限を読む。値そのものは見ない）。
   期限なしの鍵・読めなかった時は null。毎朝の回で呼び、21日を切ったらメールで知らせる */
export function daysLeft(expHeader, ms) {
  const t = Date.parse(String(expHeader || "").replace(" UTC", "Z").replace(" ", "T"));
  return isFinite(t) ? Math.floor((t - (Number(ms) || Date.now())) / 86400e3) : null;
}
export async function tokenDaysLeft(env, ms) {
  if (!env.GH_DISPATCH_TOKEN) return null;
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}`, { headers: { Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "kajikeiba-autopost" } });
    return daysLeft(r.headers.get("github-authentication-token-expiration"), ms);
  } catch { return null; }
}
