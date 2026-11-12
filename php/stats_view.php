<?php
/* 計測結果の確認画面（運営用）
 *
 * ★公開ページからリンクしない★
 *   robots.txt でも .htaccess でも隠していないので、URLを知っている人は見られる。
 *   個人を特定できる情報は保存していない（stats.php 参照）ため実害は小さいが、
 *   公開サイトの一部として扱わないこと。
 *
 * 使い方: /stats_view.php?days=14
 */
const LOG_DIR = __DIR__ . '/logs';
$days = isset($_GET['days']) ? max(1, min(90, (int)$_GET['days'])) : 14;

$byDay = $byPath = $byRef = $byDev = [];
$uniq = [];
for ($i = 0; $i < $days; $i++) {
  $d = date('Ymd', strtotime("-$i day"));
  $f = LOG_DIR . "/$d.tsv";
  if (!is_file($f)) { $byDay[$d] = [0, 0]; continue; }
  $pv = 0; $u = [];
  foreach (file($f, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
    $c = explode("\t", $line);
    if (count($c) < 5) continue;
    $pv++;
    $u[$c[4]] = true;
    $byPath[$c[1]] = ($byPath[$c[1]] ?? 0) + 1;
    $byRef[$c[2]]  = ($byRef[$c[2]]  ?? 0) + 1;
    $byDev[$c[3]]  = ($byDev[$c[3]]  ?? 0) + 1;
  }
  $byDay[$d] = [$pv, count($u)];
}
arsort($byPath); arsort($byRef); arsort($byDev);
$totPv = array_sum(array_column($byDay, 0));
$e = fn($s) => htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');

/* 検索流入の比率。BUSINESS.md の判断指標（3か月で40%以上）に対応する */
$search = 0;
foreach ($byRef as $h => $n) {
  if (preg_match('/google|yahoo|bing|duckduckgo/i', $h)) $search += $n;
}
$ext = $totPv - ($byRef['internal'] ?? 0);
?>
<!doctype html><meta charset="utf-8"><title>アクセス — カジ競馬（運営用）</title>
<meta name="robots" content="noindex,nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{background:#0a0e16;color:#fff;font-family:"Noto Sans JP",sans-serif;
  font-size:16px;line-height:1.7;margin:0;padding:20px}
h1{font-size:24px}h2{font-size:19px;margin-top:32px;border-left:4px solid #ffd43d;padding-left:10px}
table{border-collapse:collapse;width:100%;max-width:720px;margin:10px 0}
th,td{border-bottom:1px solid #333;padding:7px 8px;text-align:left}
th{color:#b3b3b3}td.n{text-align:right;font-variant-numeric:tabular-nums}
.big{font-size:30px;font-weight:700;color:#ffd43d}
.note{color:#b3b3b3}
</style>
<h1>アクセス（直近<?= $days ?>日）</h1>
<p><span class="big"><?= number_format($totPv) ?></span> PV</p>
<p class="note">Cookieなし・IP非保存・クローラ除外。訪問者数は日ごとの概数。</p>

<h2>判断指標（docs/BUSINESS.md）</h2>
<table>
<tr><th>指標</th><th class="n">現在</th><th class="n">3か月後の目安</th></tr>
<tr><td>月間PV（直近<?= $days ?>日から換算）</td>
    <td class="n"><?= number_format(round($totPv / $days * 30)) ?></td><td class="n">30,000</td></tr>
<tr><td>検索流入の比率</td>
    <td class="n"><?= $ext ? round(100 * $search / $ext) : 0 ?>%</td><td class="n">40%</td></tr>
</table>

<h2>日別</h2>
<table><tr><th>日付</th><th class="n">PV</th><th class="n">訪問者</th></tr>
<?php foreach ($byDay as $d => [$pv, $u]): ?>
<tr><td><?= $e(substr($d,0,4).'-'.substr($d,4,2).'-'.substr($d,6,2)) ?></td>
<td class="n"><?= number_format($pv) ?></td><td class="n"><?= number_format($u) ?></td></tr>
<?php endforeach ?></table>

<h2>よく見られたページ</h2>
<table><tr><th>パス</th><th class="n">PV</th></tr>
<?php foreach (array_slice($byPath, 0, 25, true) as $p => $n): ?>
<tr><td><?= $e($p) ?></td><td class="n"><?= number_format($n) ?></td></tr>
<?php endforeach ?></table>

<h2>流入元</h2>
<table><tr><th>参照元</th><th class="n">PV</th></tr>
<?php foreach (array_slice($byRef, 0, 20, true) as $p => $n): ?>
<tr><td><?= $e($p) ?></td><td class="n"><?= number_format($n) ?></td></tr>
<?php endforeach ?></table>

<h2>端末</h2>
<table><tr><th>端末</th><th class="n">PV</th></tr>
<?php foreach ($byDev as $p => $n): ?>
<tr><td><?= $e($p === 'sp' ? 'スマホ' : 'PC') ?></td><td class="n"><?= number_format($n) ?></td></tr>
<?php endforeach ?></table>
