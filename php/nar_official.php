<?php
/* 地方競馬の当日データを keiba.go.jp（公式）から取る
 *
 * ■ なぜ作るのか
 *   これまでレース表示は netkeiba のHTMLに依存していた。
 *   ・第三者のコンテンツに依存しており、AdSense の規約上のリスクがある
 *   ・相手のHTML改修でいつでも壊れる（1日で落とし穴を10件以上踏んだ）
 *   ・遮断されたら何も出せなくなる
 *
 *   地方競馬全国協会（keiba.go.jp）は公式の主催者側で、
 *   **同じ内容がより多い情報つきで公開されている**:
 *     着順・枠・馬番・馬名・所属・性齢・負担重量・騎手(所属)・調教師・
 *     馬体重(増減)・タイム・着差・上がり3F・コーナー通過順・人気・単勝オッズ
 *   netkeiba には無い「所属」「コーナー通過順」まで最初から入っている。
 *
 * ■ 使い方
 *   /nar_official.php?date=20260719                 その日の開催一覧
 *   /nar_official.php?date=20260719&baba=10&race=10 1レースの出馬表/結果
 *
 * ■ キャッシュ
 *   公式に毎回取りに行かない。発走前は短く、確定後は長く持つ。
 */

const CACHE_DIR = __DIR__ . '/cache';
const TTL_LIVE  = 120;      // 確定前は2分
const TTL_DONE  = 86400;    // 確定後は1日

header('Content-Type: application/json; charset=UTF-8');
header('Cache-Control: public, max-age=60');

$date = preg_replace('/[^0-9]/', '', $_GET['date'] ?? '');
$baba = preg_replace('/[^0-9]/', '', $_GET['baba'] ?? '');
$race = preg_replace('/[^0-9]/', '', $_GET['race'] ?? '');
if (strlen($date) !== 8) {
  http_response_code(400);
  echo json_encode(['error' => 'date は YYYYMMDD'], JSON_UNESCAPED_UNICODE);
  exit;
}
$d = substr($date, 0, 4) . '%2f' . substr($date, 4, 2) . '%2f' . substr($date, 6, 2);

function fetch_url(string $url): string {
  $ch = curl_init($url);
  curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true, CURLOPT_FOLLOWLOCATION => true,
    CURLOPT_TIMEOUT => 25, CURLOPT_CONNECTTIMEOUT => 10, CURLOPT_ENCODING => '',
    CURLOPT_USERAGENT => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
  ]);
  $b = curl_exec($ch);
  curl_close($ch);
  return is_string($b) ? $b : '';
}

function cached(string $key, int $ttl, callable $fn): string {
  if (!is_dir(CACHE_DIR)) { @mkdir(CACHE_DIR, 0755, true); }
  $f = CACHE_DIR . '/nar_' . preg_replace('/[^a-z0-9_]/i', '', $key) . '.html';
  if (is_file($f) && (time() - filemtime($f)) < $ttl) {
    $c = file_get_contents($f);
    if ($c !== false && $c !== '') return $c;
  }
  $v = $fn();
  if ($v !== '') { @file_put_contents($f, $v, LOCK_EX); }
  elseif (is_file($f)) { $v = (string)file_get_contents($f); }   // 取得失敗時は古くても返す
  return $v;
}

/* ★表は tr/td で読む★
   最初テキストに落として行で割ろうとしたが、公式ページは
   ・見出しが2行に割れる（「負担」「重量」／「上がり」「3F」）
   ・1着は着差が空、コーナー通過順が無いレースもある
   ため、行数が揃わず1件も取れなかった。
   td を数えるほうが構造変更にも強い。 */
function cellsOf(string $tr): array {
  $out = [];
  if (preg_match_all('#<t[dh][^>]*>(.*?)</t[dh]>#su', $tr, $m)) {
    foreach ($m[1] as $c) {
      $v = html_entity_decode(strip_tags($c), ENT_QUOTES, 'UTF-8');
      $v = str_replace(["\xc2\xa0", "　"], ' ', $v);
      $out[] = trim(preg_replace('/\s+/u', ' ', $v));
    }
  }
  return $out;
}

/* ---- ① 開催一覧 ---- */
if ($baba === '') {
  $html = cached("list_$date", TTL_LIVE, fn() => fetch_url(
    "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceList?k_raceDate=$d"));
  preg_match_all('/k_babaCode=(\d+)/', $html, $m);
  echo json_encode(['date' => $date, 'baba' => array_values(array_unique($m[1] ?? []))],
                   JSON_UNESCAPED_UNICODE);
  exit;
}

/* ---- ② 1レース ---- */
$key = "mark_{$date}_{$baba}_{$race}";
$html = cached($key, TTL_LIVE, fn() => fetch_url(
  "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable"
  . "?k_raceDate=$d&k_raceNo=$race&k_babaCode=$baba"));

$hasResult = (strpos($html, '着順') !== false);

/* 出走馬の行 = td が10個以上ある tr。見出し行やナビは自然に落ちる */
$horses = [];
if (preg_match_all('#<tr[^>]*>(.*?)</tr>#su', $html, $mm)) {
  foreach ($mm[1] as $tr) {
    $c = cellsOf($tr);
    if (count($c) < 10) continue;
    if (!preg_match('/^\d+$/', $c[0])) continue;   // 先頭が数字でない行は表以外
    // 騎手欄は「高松亮 （岩手）」の形。名前と所属に割る
    $jk = $c[7] ?? '';
    $jkName = trim(preg_replace('/（.*?）/u', '', $jk));
    preg_match('/（(.*?)）/u', $jk, $jm);
    // 馬体重「484 (6)」
    preg_match('/(\d{3})\s*\(([-+]?\d+)\)/', $c[9] ?? '', $wm);
    $horses[] = $hasResult ? [
      'rank' => (int)$c[0], 'waku' => (int)$c[1], 'num' => (int)$c[2],
      'name' => $c[3], 'belong' => $c[4], 'sexAge' => $c[5], 'kg' => $c[6],
      'jockey' => $jkName, 'jockeyBelong' => $jm[1] ?? '',
      'trainer' => $c[8] ?? '', 'weight' => $wm[1] ?? null, 'diff' => $wm[2] ?? null,
      'time' => $c[10] ?? '', 'margin' => $c[11] ?? '', 'last3f' => $c[12] ?? '',
      'corner' => $c[13] ?? '', 'pop' => $c[14] ?? '', 'odds' => $c[15] ?? '',
    ] : [
      'waku' => (int)$c[0], 'num' => (int)$c[1], 'name' => $c[2],
      'belong' => $c[3] ?? '', 'sexAge' => $c[4] ?? '', 'kg' => $c[5] ?? '',
      'jockey' => $jkName, 'trainer' => $c[7] ?? '',
    ];
  }
}

/* レース名・条件（見出し部分から拾う） */
$title = '';
if (preg_match('#<h[12][^>]*>(.*?)</h[12]>#su', $html, $tm)) {
  $title = trim(preg_replace('/\s+/u', ' ',
    html_entity_decode(strip_tags($tm[1]), ENT_QUOTES, 'UTF-8')));
}

$out = ['date' => $date, 'baba' => $baba, 'race' => (int)$race,
        'title' => $title, 'hasResult' => $hasResult, 'horses' => $horses];
$out['source'] = '地方競馬全国協会（keiba.go.jp）';
echo json_encode($out, JSON_UNESCAPED_UNICODE);
