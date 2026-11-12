<?php
/* seventh-well.com/odds/proxy.php
   netkeiba取得用の自前プロキシ（クリーンIP・同一オリジン）

   ■ 使い方（2通り。どちらでも動く）
     推奨: proxy.php?u=<Base64URL(対象URL)>     ← WAF回避用
           （?url=https://... の形は お名前.comのWAFにSSRF攻撃と誤判定されブロックされる）
     旧式: proxy.php?url=<URLエンコード(対象URL)> ← 後方互換

   ■ Base64URL: 標準Base64の "+/" を "-_" に置換し、末尾の "=" を除去したもの
*/

// --- 対象URLの取得（u= を優先、無ければ url=） ---
$url = '';
if (isset($_GET['u']) && $_GET['u'] !== '') {
  $b = strtr((string)$_GET['u'], '-_', '+/');       // Base64URL → 標準Base64
  $pad = strlen($b) % 4;
  if ($pad) { $b .= str_repeat('=', 4 - $pad); }     // パディング復元
  $decoded = base64_decode($b, true);
  if ($decoded !== false) { $url = $decoded; }
} elseif (isset($_GET['url'])) {
  $url = (string)$_GET['url'];
}

// --- ホワイトリスト検証（netkeiba系のみ許可） ---
if ($url === '' || !preg_match('#^https://[a-z0-9.-]*\.(netkeiba|keeeeeeba)\.com/#i', $url)) {
  http_response_code(400);
  header('Access-Control-Allow-Origin: *');
  echo 'bad url';
  exit;
}

/* --- サーバー側キャッシュ（★2026-07-21追加★） ---
   netkeiba がレート制限/一時ブロックで 400/502 を返すと、no-store のままでは
   毎回そのまま利用者に流れて即死する（実際に起きた障害）。
   一度でも成功した本文を短時間キャッシュしておき、取得失敗時はそれを
   「無いよりまし」で返す（新しい取得を最優先、失敗時だけフォールバック）。
   ページの鮮度が命の当日オッズ等も、TTLを短くすれば実害は小さい。 */
const PX_CACHE_DIR = __DIR__ . '/cache/proxy';
const PX_TTL_FRESH  = 90;     // この秒数以内なら新規取得よりキャッシュを優先（同じURL連打の負荷軽減）
const PX_TTL_STALE  = 21600;  // 取得失敗時、これより新しければ「古くても」フォールバックに使う（6時間）

/* ★2026-07-24追加★ レース結果ページはSTALEフォールバック対象から除外する。
   発走前に「まだ結果なし」の正常ページを一度キャッシュした後、レース確定後に
   直接取得もjina中継も失敗する（一括取得の連打でnetkeiba/jinaがレート制限に
   引っかかりやすい）と、STALEフォールバックが古い「結果なし」を最大6時間
   返し続け、確定後もずっと「結果待ち」のまま止まって見えるバグがあった
   （tweet.htmlのcache:"no-store"コメント・results.phpのnginxキャッシュ修正と
   同じ症状が、proxy.php自身のファイルキャッシュでも起きていた）。
   結果ページだけはSTALE不使用にして、失敗時は素直にエラーを返す
   （クライアント側の複数プロキシ再試行に委ねる）。90秒のFRESH短絡はそのまま
   （連打の負荷軽減として無害）。 */
function px_is_volatile(string $url): bool {
  return (bool)preg_match('#/race/result\.html#', $url);
}
$PX_VOLATILE = px_is_volatile($url);

function px_key(string $url): string {
  return __DIR__ . '/cache/proxy/' . sha1($url) . '.cache';
}
function px_read(string $f): ?array {
  if (!is_file($f)) return null;
  $raw = @file_get_contents($f);
  if ($raw === false || $raw === '') return null;
  $nl = strpos($raw, "\n");
  if ($nl === false) return null;
  $head = json_decode(substr($raw, 0, $nl), true);
  if (!$head) return null;
  return ['code' => $head['code'], 'ctype' => $head['ctype'],
          'body' => substr($raw, $nl + 1), 'age' => time() - filemtime($f)];
}
function px_write(string $f, int $code, string $ctype, string $body): void {
  if (!is_dir(PX_CACHE_DIR)) { @mkdir(PX_CACHE_DIR, 0775, true); }
  @file_put_contents($f, json_encode(['code' => $code, 'ctype' => $ctype], JSON_UNESCAPED_UNICODE) . "\n" . $body, LOCK_EX);
}

$cf = px_key($url);
$cached = px_read($cf);

// 直近すぎるなら再取得せずキャッシュを返す（連打の負荷軽減。失敗レスポンスは使わない）
if ($cached && $cached['age'] < PX_TTL_FRESH && $cached['code'] >= 200 && $cached['code'] < 400) {
  header('Access-Control-Allow-Origin: *');
  header('Cache-Control: no-store');
  header('X-Proxy-Cache: fresh');
  if ($cached['ctype']) { header('Content-Type: ' . $cached['ctype']); }
  http_response_code($cached['code']);
  echo $cached['body'];
  exit;
}

// --- 取得 ---
$ch = curl_init($url);
curl_setopt_array($ch, [
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_FOLLOWLOCATION => true,
  CURLOPT_TIMEOUT        => 20,
  CURLOPT_CONNECTTIMEOUT => 10,
  CURLOPT_ENCODING       => '',
  CURLOPT_USERAGENT      => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
  CURLOPT_HTTPHEADER     => ['Accept: text/html,application/xhtml+xml,*/*', 'Accept-Language: ja,en;q=0.8', 'Referer: https://nar.netkeiba.com/'],
]);
$body  = curl_exec($ch);
$code  = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
$ctype = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
curl_close($ch);

header('Access-Control-Allow-Origin: *');
header('Cache-Control: no-store');
if ($ctype) { header('Content-Type: ' . $ctype); }

$ok = ($body !== false && $code >= 200 && $code < 400 && strlen($body) > 200);
if ($ok) {
  px_write($cf, $code, (string)$ctype, $body);
  header('X-Proxy-Cache: miss');
  http_response_code($code);
  echo $body;
  exit;
}

/* --- ② 中継(r.jina.ai)経由で再試行（★2026-07-21追加★） ---
   netkeibaがこのサーバーのIPをブロックしても、r.jina.ai（別IP帯）経由なら届く
   ことを実測済み（Cloudflare WorkerのIP帯は弾かれるがjinaは通る）。
   直接取得が失敗した時だけ使う。JSONは<html><body>で包まれて返るので剥がす。
   ※無料枠は20req/分。通常閲覧なら足りるが、大量取得には絶対使わない。 */
function px_jina(string $url, bool $htmlMode): array {
  $jr = curl_init('https://r.jina.ai/' . $url);
  $hdr = ['Accept: text/html,application/json,*/*'];
  if ($htmlMode) { $hdr[] = 'X-Return-Format: html'; }
  curl_setopt_array($jr, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 30,
    CURLOPT_CONNECTTIMEOUT => 10,
    CURLOPT_ENCODING       => '',
    CURLOPT_USERAGENT      => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    CURLOPT_HTTPHEADER     => $hdr,
  ]);
  $b = curl_exec($jr);
  $c = (int)curl_getinfo($jr, CURLINFO_HTTP_CODE);
  curl_close($jr);
  return [$b, $c];
}
// html モードで取得。AJAX断片(race_list_sub等)はブラウザ描画で空になるので、
// 小さすぎたら markdown モード（生テキスト・race_id等はそのまま残る）で再試行。
list($jbody, $jcode) = px_jina($url, true);
if (!($jbody !== false && $jcode === 200 && strlen($jbody) > 1000)) {
  list($jb2, $jc2) = px_jina($url, false);
  if ($jb2 !== false && $jc2 === 200 && strlen($jb2) > strlen((string)$jbody)) {
    $jbody = $jb2; $jcode = $jc2;
  }
}
if (isset($_GET['diag'])) {   // 一時診断: 直接とjinaの生の結果を返す
  header('Content-Type: application/json');
  echo json_encode(['direct_code' => $code, 'direct_len' => is_string($body)?strlen($body):-1,
                    'jina_code' => $jcode, 'jina_len' => is_string($jbody)?strlen($jbody):-1,
                    'jina_err' => $jbody === false ? 'curl_false' : substr((string)$jbody,0,120)]);
  exit;
}
if ($jbody !== false && $jcode === 200 && strlen($jbody) > 200) {
  // jinaはJSON応答を <html><head></head><body>…</body></html> で包む → 剥がす
  if (preg_match('#^<html><head></head><body>(.*)</body></html>\s*$#s', $jbody, $jm)) {
    $jbody = $jm[1];
  }
  // markdownモードは "Title: …\nURL Source: …\nMarkdown Content:\n<中身>" で包む → JSONなら剥がす
  if (preg_match('#^Title:.*?Markdown Content:\s*\n(.*)$#s', $jbody, $jm2)) {
    $inner = trim($jm2[1]);
    if ($inner !== '' && ($inner[0] === '{' || $inner[0] === '[')) { $jbody = $inner; }
  }
  $lt = ltrim($jbody);
  $jct = ($lt !== '' && ($lt[0] === '{' || $lt[0] === '['))
       ? 'application/json; charset=UTF-8' : 'text/html; charset=UTF-8';
  // ★劣化上書きガード★ リレー(markdown等)は完全なHTMLより情報が少ないことがある。
  //   既存キャッシュより大幅に小さい結果でproxy_seedの良キャッシュを潰さない
  //   （実際: 36Rの完全一覧35KBが、リレーmarkdown12R/20KBに上書きされ「門別しか出ない」事故）。
  $worse = ($cached && strlen($jbody) < strlen($cached['body']) * 0.6);
  if (!$worse) { px_write($cf, 200, $jct, $jbody); }
  elseif (!$PX_VOLATILE && $cached['age'] < PX_TTL_STALE) {
    header('X-Proxy-Cache: stale-kept');           // 良いキャッシュを保持してそれを返す
    if ($cached['ctype']) { header('Content-Type: ' . $cached['ctype']); }
    http_response_code(200);
    echo $cached['body'];
    exit;
  }
  header('X-Proxy-Cache: relay');
  header('Content-Type: ' . $jct);
  http_response_code(200);
  echo $jbody;
  exit;
}

// ③ 取得失敗（400/502/レート制限等） → 古くてもキャッシュがあればそれを返す（無いよりまし）
//    ただしレース結果ページ($PX_VOLATILE)は対象外（上のコメント参照）。
if (!$PX_VOLATILE && $cached && $cached['age'] < PX_TTL_STALE && $cached['code'] >= 200 && $cached['code'] < 400) {
  header('X-Proxy-Cache: stale-fallback');
  if ($cached['ctype']) { header('Content-Type: ' . $cached['ctype']); }
  http_response_code(200);
  echo $cached['body'];
  exit;
}

if ($body === false || $code === 0) { http_response_code(502); echo 'fetch failed'; exit; }
http_response_code($code ?: 200);
echo $body;
