<?php
/* =====================================================================
   ODDS ANOMALY — 学習ログ保存 API  (PHP + フラットJSON)
   お名前.com 等の共有ホスティング向け。DB不要。
   設置例: https://seventh-well.com/odds/odds-log.php

   ルート（?action=...）:
     GET  ?action=list            → 全レコード {records:[...]}
     POST ?action=put   body=rec  → 1レコード保存/更新（id一致で上書き）
     POST ?action=bulk  body=[..] → 複数まとめて保存/更新
     GET  ?action=stats           → 件数など軽い情報

   レコード形式（アプリ側と一致）:
     {id, mode, track, no, going, surface, dist, ts,
      picks:[{num,name,jockey,score,tags,totalPct,recentPct}],
      result:{win,place3,winWaku,winPop,winTimeSec,winLast3f,winJockey,fetched}|null}
   ===================================================================== */

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET,POST,OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

/* 保存先。書き込み権限のある場所に。スクリプトと同じディレクトリの data/ */
$DIR  = __DIR__ . '/data';
$MAX  = 5000;   // 保持上限（古いものから捨てる）
if (!is_dir($DIR)) { @mkdir($DIR, 0755, true); }

/* mode別にファイルを分ける（jra / nar）。?mode= で指定、既定は jra */
$mode = (isset($_GET['mode']) && $_GET['mode'] === 'nar') ? 'nar' : 'jra';
$FILE = $DIR . "/odds_log_{$mode}.json";
$LOCK = $DIR . "/odds_log_{$mode}.lock";

function out($obj, $code = 200) { http_response_code($code); echo json_encode($obj, JSON_UNESCAPED_UNICODE); exit; }

function load_all($FILE) {
  if (!file_exists($FILE)) return [];
  $raw = file_get_contents($FILE);
  $j = json_decode($raw, true);
  return is_array($j) ? $j : [];
}

/* 排他ロック付き書き込み（共有ホスティングの同時アクセス対策） */
function save_all($FILE, $LOCK, $records, $MAX) {
  if (count($records) > $MAX) $records = array_slice($records, -$MAX);
  $fp = fopen($LOCK, 'c');
  if ($fp) { flock($fp, LOCK_EX); }
  file_put_contents($FILE, json_encode(array_values($records), JSON_UNESCAPED_UNICODE), LOCK_EX);
  if ($fp) { flock($fp, LOCK_UN); fclose($fp); }
}

/* id一致で上書き、無ければ追加 */
function upsert(&$records, $rec) {
  if (!isset($rec['id'])) return false;
  foreach ($records as $i => $r) {
    if (isset($r['id']) && $r['id'] === $rec['id']) {
      // result は既存を保持しつつ新規が持っていれば上書き
      if (empty($rec['result']) && !empty($r['result'])) $rec['result'] = $r['result'];
      $records[$i] = $rec; return true;
    }
  }
  $records[] = $rec; return true;
}

$action = isset($_GET['action']) ? $_GET['action'] : 'list';

try {
  if ($action === 'list') {
    out(['records' => load_all($FILE)]);
  }

  if ($action === 'stats') {
    $all = load_all($FILE);
    $settled = 0; foreach ($all as $r) { if (!empty($r['result']['win'])) $settled++; }
    out(['count' => count($all), 'settled' => $settled]);
  }

  /* EUC-JP⇔UTF-8変換ヘルパ（mbstring優先、無ければiconv） */
  if (!function_exists('to_euc')) {
    function to_euc($s){ if(function_exists('mb_convert_encoding')) return mb_convert_encoding($s,'EUC-JP','UTF-8');
      if(function_exists('iconv')) return iconv('UTF-8','EUC-JP//TRANSLIT',$s); return $s; }
    function to_utf8($s){ if(function_exists('mb_convert_encoding')) return mb_convert_encoding($s,'UTF-8','EUC-JP');
      if(function_exists('iconv')) return iconv('EUC-JP','UTF-8//TRANSLIT',$s); return $s; }
  }

  /* 重賞 過去レース一覧 */
  if ($action === 'jusho_list') {
    $name = isset($_GET['name']) ? $_GET['name'] : '';
    if ($name === '') out(['editions' => []]);
    $euc = to_euc($name);
    $inner = 'https://db.netkeiba.com/?pid=race_list&word=' . rawurlencode($euc) . '&front=1';
    $url = 'https://api.codetabs.com/v1/proxy/?quest=' . rawurlencode($inner);
    $ctx = stream_context_create(['http' => ['header' => "User-Agent: Mozilla/5.0\r\n", 'timeout' => 25]]);
    $raw = @file_get_contents($url, false, $ctx);
    $editions = [];
    if ($raw !== false) {
      $html = to_utf8($raw);
      if (preg_match_all('#/race/(\d{12})/?"[^>]*>([^<]*)#', $html, $m, PREG_SET_ORDER)) {
        $seen = [];
        foreach ($m as $x) {
          $rid = $x[1]; $label = trim($x[2]);
          if (isset($seen[$rid])) continue; $seen[$rid] = 1;
          if (!preg_match('/G[I123]|\(G\d\)|重賞/u', $label)) continue;
          $editions[] = ['rid' => $rid, 'year' => substr($rid, 0, 4), 'label' => $label];
        }
      }
    }
    out(['editions' => $editions]);
  }

  /* 重賞 過去結果 */
  if ($action === 'jusho_result') {
    $rid = isset($_GET['rid']) ? preg_replace('/[^0-9]/', '', $_GET['rid']) : '';
    if ($rid === '') out(['html' => '']);
    $inner = 'https://db.netkeiba.com/race/' . $rid . '/';
    $url = 'https://api.codetabs.com/v1/proxy/?quest=' . rawurlencode($inner);
    $ctx = stream_context_create(['http' => ['header' => "User-Agent: Mozilla/5.0\r\n", 'timeout' => 25]]);
    $raw = @file_get_contents($url, false, $ctx);
    $html = ($raw !== false) ? to_utf8($raw) : '';
    out(['html' => $html]);
  }

  /* 串刺しウォッチ用ボード: cronが集めた odds_snaps.json を読み、
     アクティブ各レースの「最大急落・現在最低オッズ・頭数」を集計して返す。
     ?action=board&mode=jra|nar （mode未指定は全件） */
  if ($action === 'board') {
    $SNAP = $DIR . '/odds_snaps.json';
    $snaps = load_all($SNAP);
    $wantMode = isset($_GET['mode']) ? $_GET['mode'] : '';
    $rows = [];
    foreach ($snaps as $rid => $s) {
      if (!is_array($s) || empty($s['series'])) continue;
      if ($wantMode && isset($s['mode']) && $s['mode'] !== $wantMode) continue;
      $series = $s['series'];
      $cur = end($series); $curWin = isset($cur['win']) ? $cur['win'] : [];
      $first = $series[0]['win'];
      $prev = count($series) >= 2 ? $series[count($series)-2]['win'] : $first;
      // 各馬の総変化率(初→現)を計算し、最大の急落を拾う
      $maxDrop = 0; $dropNum = null; $minOdds = null; $minNum = null;
      foreach ($curWin as $num => $od) {
        $od = floatval($od); if ($od <= 0) continue;
        if ($minOdds === null || $od < $minOdds) { $minOdds = $od; $minNum = $num; }
        if (isset($first[$num]) && $first[$num] > 0) {
          $chg = ($od - $first[$num]) / $first[$num] * 100;
          if ($chg < $maxDrop) { $maxDrop = $chg; $dropNum = $num; }
        }
      }
      $rows[] = [
        'rid'     => $rid,
        'mode'    => isset($s['mode']) ? $s['mode'] : '',
        'track'   => isset($s['track']) ? $s['track'] : '',
        'no'      => isset($s['no']) ? intval($s['no']) : 0,
        'postMin' => isset($s['postMin']) ? intval($s['postMin']) : null,
        'horses'  => count($curWin),
        'snaps'   => count($series),
        'minOdds' => $minOdds,
        'minNum'  => $minNum,
        'maxDrop' => round($maxDrop, 1),   // 最大急落%（負値）
        'dropNum' => $dropNum,
      ];
    }
    // 急落が大きい順
    usort($rows, function($a,$b){ return $a['maxDrop'] <=> $b['maxDrop']; });
    out(['board' => $rows, 'count' => count($rows)]);
  }

  if ($action === 'put') {
    $body = json_decode(file_get_contents('php://input'), true);
    if (!is_array($body) || !isset($body['id'])) out(['error' => 'invalid record'], 400);
    $all = load_all($FILE);
    upsert($all, $body);
    save_all($FILE, $LOCK, $all, $MAX);
    out(['ok' => true, 'count' => count($all)]);
  }

  if ($action === 'bulk') {
    $body = json_decode(file_get_contents('php://input'), true);
    if (!is_array($body)) out(['error' => 'expected array'], 400);
    $all = load_all($FILE);
    $n = 0;
    foreach ($body as $rec) { if (is_array($rec) && isset($rec['id'])) { upsert($all, $rec); $n++; } }
    save_all($FILE, $LOCK, $all, $MAX);
    out(['ok' => true, 'merged' => $n, 'count' => count($all)]);
  }

  out(['error' => 'unknown action', 'actions' => ['list','put','bulk','stats','board']], 400);

} catch (Exception $e) {
  out(['error' => $e->getMessage()], 500);
}
