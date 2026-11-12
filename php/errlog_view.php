<?php
/* JSエラーログの確認画面（運営用）
 *
 * ★公開ページからリンクしない★ stats_view.php と同じ扱い。
 *   個人を特定できる情報は保存していない（error_log.php参照）ため実害は小さいが、
 *   公開サイトの一部として扱わないこと。
 *
 * 使い方: /errlog_view.php?days=7
 */

// ★実測で踏んだ罠★ nginxのキャッシュ層(X-Nginx-Cache)がこのページを丸ごとキャッシュし、
//   新しいエラーが記録された後も古い「0件」の結果を返し続けていた（本番で実測して発覚）。
//   「すぐ気づいて直せる」ためのツールが古い結果を見せては本末転倒なので、
//   毎回サーバーへ取りに行かせる（stats.phpと同じ方針）。
header('Cache-Control: no-store, no-cache, must-revalidate');
header('Pragma: no-cache');

const LOG_DIR = __DIR__ . '/logs';
$days = isset($_GET['days']) ? max(1, min(30, (int)$_GET['days'])) : 7;

$byMsg = [];   // msg => {n, pages:Set, first, last, sample}
$total = 0;
for ($i = 0; $i < $days; $i++) {
  $d = date('Ymd', strtotime("-$i day"));
  $f = LOG_DIR . "/errors_$d.jsonl";
  if (!is_file($f)) continue;
  foreach (file($f, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
    $e = json_decode($line, true);
    if (!is_array($e) || !isset($e['msg'])) continue;
    $total++;
    $key = $e['msg'];
    if (!isset($byMsg[$key])) {
      $byMsg[$key] = ['n' => 0, 'pages' => [], 'first' => $e['t'] ?? '', 'last' => $e['t'] ?? '', 'stack' => $e['stack'] ?? ''];
    }
    $byMsg[$key]['n']++;
    $byMsg[$key]['pages'][$e['page'] ?? ''] = true;
    $byMsg[$key]['last'] = $e['t'] ?? $byMsg[$key]['last'];
  }
}
uasort($byMsg, fn($a, $b) => $b['n'] - $a['n']);
$esc = fn($s) => htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');
?>
<!doctype html><meta charset="utf-8"><title>JSエラー — カジ競馬（運営用）</title>
<meta name="robots" content="noindex,nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{background:#0a0e16;color:#fff;font-family:"Noto Sans JP",sans-serif;
  font-size:15px;line-height:1.7;margin:0;padding:20px}
h1{font-size:24px}
.big{font-size:30px;font-weight:700;color:<?= $total ? '#ff7171' : '#51b883' ?>}
.note{color:#b3b3b3}
.card{background:#12161f;border:1px solid #262b38;border-radius:10px;padding:14px 16px;margin:12px 0}
.card .msg{font-family:"Space Mono",monospace;font-size:14px;color:#ffd43d;word-break:break-all}
.card .meta{color:#b3b3b3;font-size:13px;margin-top:6px}
.card .pages{color:#7ec8f0;font-size:13px;margin-top:4px;word-break:break-all}
.card details{margin-top:8px}
.card pre{white-space:pre-wrap;word-break:break-all;font-size:12px;color:#b3b3b3;
  background:#0a0e16;padding:8px;border-radius:6px;max-height:200px;overflow-y:auto}
</style>
<h1>JSエラー（直近<?= $days ?>日）</h1>
<p><span class="big"><?= number_format($total) ?></span> 件 / <?= count($byMsg) ?>種類</p>
<p class="note">error_log.phpが受け取ったクライアント側の例外。1日あたり最大500件まで記録（それ以上は捨てる）。<br>
Cookieなし・IP非保存。エラーメッセージの内容ごとにまとめて表示（多い順）。</p>

<?php if (!$byMsg): ?>
<p class="note">この期間、記録されたエラーはありません。</p>
<?php else: foreach ($byMsg as $msg => $info): ?>
<div class="card">
  <div class="msg"><?= $esc($msg) ?></div>
  <div class="meta">
    <?= number_format($info['n']) ?>件 ／ 最初 <?= $esc($info['first']) ?> ／ 最後 <?= $esc($info['last']) ?>
  </div>
  <div class="pages">発生ページ: <?= $esc(implode(' , ', array_keys($info['pages']))) ?></div>
  <?php if ($info['stack']): ?>
  <details><summary>スタックトレース（代表1件）</summary><pre><?= $esc($info['stack']) ?></pre></details>
  <?php endif ?>
</div>
<?php endforeach; endif ?>
