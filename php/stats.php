<?php
/* アクセス計測（自前・Cookieなし・第三者に渡さない）
 *
 * ★なぜ自前なのか★
 *   PV・流入元が分からないまま価格も広告も決められない（いま何も計測していない）。
 *   一方で、外部の解析サービスを入れると訪問者のデータが第三者に渡り、
 *   同意バナーも要る。ここで欲しいのは「どのページが読まれ、どこから来たか」だけ。
 *   それなら自前で足りる。
 *
 * ★個人を特定できる情報は保存しない★
 *   ・Cookie を発行しない
 *   ・IPアドレスは保存しない（1日単位の塩でハッシュ化し、訪問者の概数だけ数える）
 *     塩は日付で変わるので、日をまたいで同一人物を追跡できない
 *   ・User-Agent は「スマホ/PC」の判定にだけ使い、生では残さない
 *
 * 記録先: logs/YYYYMMDD.tsv （1行1PV）
 *   時刻 \t パス \t 参照元ホスト \t 端末 \t 訪問者ハッシュ
 */

const LOG_DIR = __DIR__ . '/logs';

// 1x1 の透明GIF を返す（本文は極小・キャッシュさせない）
header('Content-Type: image/gif');
header('Cache-Control: no-store, no-cache, must-revalidate');
header('Pragma: no-cache');
$gif = base64_decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7');
echo $gif;

// 以降は記録処理（失敗しても画面には影響させない）
if (function_exists('fastcgi_finish_request')) { fastcgi_finish_request(); }

$path = isset($_GET['p']) ? (string)$_GET['p'] : '';
$ref  = isset($_GET['r']) ? (string)$_GET['r'] : '';

// パスは自サイト内のものだけ受け付ける（外部から任意の文字列を書き込ませない）
$path = preg_replace('#[^0-9a-zA-Z/_\-.?=&]#', '', $path);
$path = mb_substr($path, 0, 120);
if ($path === '' || $path[0] !== '/') { exit; }

// 参照元はホスト名だけ（クエリに個人情報が乗ることがあるので落とす）
$refHost = '';
if ($ref !== '') {
  $h = parse_url($ref, PHP_URL_HOST);
  if (is_string($h)) { $refHost = preg_replace('/[^0-9a-zA-Z.\-]/', '', $h); }
}
if ($refHost === '' ) { $refHost = 'direct'; }
if (strpos($refHost, 'kajikeiba.com') !== false) { $refHost = 'internal'; }

$ua = isset($_SERVER['HTTP_USER_AGENT']) ? $_SERVER['HTTP_USER_AGENT'] : '';
// 明らかなクローラは数えない（PVを水増ししない）
if (preg_match('/bot|crawler|spider|slurp|bingpreview|facebookexternalhit/i', $ua)) { exit; }
$device = preg_match('/iPhone|Android|Mobile/i', $ua) ? 'sp' : 'pc';

// 訪問者の概数用ハッシュ。日ごとに塩が変わるので翌日は別人扱いになる（追跡しない）
$ip   = isset($_SERVER['REMOTE_ADDR']) ? $_SERVER['REMOTE_ADDR'] : '';
$salt = date('Ymd') . '|kajikeiba|' . __FILE__;
$vid  = substr(hash('sha256', $salt . $ip . $device), 0, 12);

if (!is_dir(LOG_DIR)) { @mkdir(LOG_DIR, 0755, true); }
$line = implode("\t", [date('H:i:s'), $path, $refHost, $device, $vid]) . "\n";
@file_put_contents(LOG_DIR . '/' . date('Ymd') . '.tsv', $line, FILE_APPEND | LOCK_EX);
