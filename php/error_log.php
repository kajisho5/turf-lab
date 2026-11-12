<?php
/* クライアント側JSエラーの収集（自前・運営がすぐ気づいて直せるように）
 *
 * ★なぜ要るか★
 *   本番でJSエラーが起きても、運営が自分のブラウザのコンソールを見ない限り気づけない。
 *   フォロワー側の端末で起きたエラーは尚更分からない。ここに集めて
 *   errlog_view.php で一覧できるようにする。
 *
 * ★安全策（stats.phpと同じ方針）★
 *   ・POSTかつJSONのみ受け付ける。読み取りは8KB上限
 *   ・各フィールドは長さを切り詰め、制御文字を除去してから1行のJSONとして保存
 *   ・1日1ファイル・1日あたりの行数に上限（暴走/スパムでディスクを食い潰さない）
 *   ・個人を特定できる情報は保存しない（IPは保存しない）
 *   ・失敗しても常に200を返す（呼び出し元はfetch keepaliveの投げっぱなしのため）
 *
 * 記録先: logs/errors_YYYYMMDD.jsonl （1行1件のJSON）
 */

const LOG_DIR = __DIR__ . '/logs';
const MAX_LINES_PER_DAY = 500;   // 暴走時の歯止め
const MAX_BODY_BYTES = 8192;

header('Content-Type: application/json');
header('Cache-Control: no-store, no-cache, must-revalidate');

function done($ok) { echo json_encode(['ok' => $ok]); exit; }

if ($_SERVER['REQUEST_METHOD'] !== 'POST') { done(false); }

$raw = file_get_contents('php://input', false, null, 0, MAX_BODY_BYTES);
$data = json_decode((string)$raw, true);
if (!is_array($data)) { done(false); }

$clip = function ($s, $len) {
  $s = is_string($s) ? $s : '';
  $s = preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F]/', '', $s);   // 制御文字除去（改行は残す）
  $s = str_replace(["\r\n", "\r"], "\n", $s);
  return mb_substr($s, 0, $len);
};

$entry = [
  't'     => date('c'),
  'page'  => $clip($data['page'] ?? '', 200),
  'msg'   => $clip($data['msg'] ?? '', 500),
  'stack' => $clip($data['stack'] ?? '', 2000),
  'ua'    => $clip($_SERVER['HTTP_USER_AGENT'] ?? '', 200),
];
if ($entry['page'] === '' || $entry['msg'] === '') { done(false); }

if (!is_dir(LOG_DIR)) { @mkdir(LOG_DIR, 0755, true); }
$file = LOG_DIR . '/errors_' . date('Ymd') . '.jsonl';

// 1日の行数に上限（厳密なロックはせず概算チェック。多少のズレは許容）
$lineCount = 0;
if (is_file($file)) {
  $lineCount = count(file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES));
}
if ($lineCount >= MAX_LINES_PER_DAY) { done(false); }

$json = json_encode($entry, JSON_UNESCAPED_UNICODE);
if ($json === false) { done(false); }
@file_put_contents($file, $json . "\n", FILE_APPEND | LOCK_EX);
done(true);
