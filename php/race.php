<?php
/* kajikeiba.com — レース詳細（★サーバー側でも中身を出す★）
 *
 * ■ なぜ作るのか
 *   これまで /race.html?id=... はJSで後から中身を入れていた。
 *   その結果、検索エンジンが見るHTMLは
 *     <title>レース詳細 — カジ競馬</title>（全レース同一）
 *     <h1>読み込み中…</h1>
 *     馬名は1つも含まれない
 *   という状態で、しかも noindex まで付けていた。
 *   競馬メディアの検索流入は「レース名＋出馬表／結果」のロングテールで
 *   成り立っており、1日36〜80レース×365日＝年2万ページぶんの資産を捨てていた。
 *
 * ■ 方針
 *   ・レース名・出走馬・着順・払戻を**サーバー側でHTMLに出す**
 *   ・title / description をレースごとに出し分ける
 *   ・JSはその上に乗せて、AI予想などの動的部分を足す（二重描画はしない）
 *
 * ■ キャッシュは必須
 *   クローラが来るたびに netkeiba を叩くと、相手にも自分にも負荷がかかる。
 *   ファイルキャッシュを挟む。発走前は短く、確定後は長く持つ。
 *
 * ■ 使い方
 *   /race/202602011212/     （.htaccess で書き換え）
 *   /race.php?id=202602011212
 */

const CACHE_DIR   = __DIR__ . '/cache';
const TTL_LIVE    = 180;      // 発走前・確定前は3分
const TTL_DONE    = 86400;    // 確定後は1日（結果は変わらない）

$rid = isset($_GET['id']) ? preg_replace('/[^0-9]/', '', (string)$_GET['id']) : '';
if (strlen($rid) !== 12) {
  http_response_code(404);
  header('Content-Type: text/html; charset=UTF-8');
  echo '<meta charset="utf-8"><title>レースが見つかりません — カジ競馬</title>'
     . '<p>レースが見つかりません。<a href="/">レース一覧へ</a></p>';
  exit;
}

/* 中央か地方か。場コード(5〜6桁目)が 01〜10 なら中央 */
$jyo   = (int)substr($rid, 4, 2);
$isJra = ($jyo >= 1 && $jyo <= 10);
$host  = $isJra ? 'race.netkeiba.com' : 'nar.netkeiba.com';

function fetch_url(string $url): string {
  $ch = curl_init($url);
  curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_FOLLOWLOCATION => true,
    CURLOPT_TIMEOUT        => 20,
    CURLOPT_CONNECTTIMEOUT => 10,
    CURLOPT_ENCODING       => '',
    CURLOPT_USERAGENT      => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    CURLOPT_HTTPHEADER     => ['Accept: text/html,*/*', 'Accept-Language: ja,en;q=0.8'],
  ]);
  $b = curl_exec($ch);
  curl_close($ch);
  return is_string($b) ? $b : '';
}

/* キャッシュ付き取得 */
function cached(string $key, int $ttl, callable $fn): string {
  if (!is_dir(CACHE_DIR)) { @mkdir(CACHE_DIR, 0755, true); }
  $f = CACHE_DIR . '/' . preg_replace('/[^a-z0-9_]/i', '', $key) . '.html';
  if (is_file($f) && (time() - filemtime($f)) < $ttl) {
    $c = file_get_contents($f);
    if ($c !== false && $c !== '') return $c;
  }
  $v = $fn();
  if ($v !== '') { @file_put_contents($f, $v, LOCK_EX); }
  elseif (is_file($f)) { $v = (string)file_get_contents($f); }  // 取得失敗時は古くても出す
  return $v;
}

/* --- 取得（結果が出ていれば結果、無ければ出馬表） --- */
$result = cached("res_$rid", TTL_LIVE, fn() => fetch_url("https://$host/race/result.html?race_id=$rid"));
// ★地方の結果行には HorseList クラスが無い★
//   クラスで判定すると地方だけ永久に「結果なし」になる。
//   着順セル(Result_Num)の有無で見る。これは中央・地方の両方にある。
$hasResult = (strpos($result, 'All_Result_Table') !== false)
          && (preg_match('/class="Result_Num"/', $result) === 1);

if ($hasResult) {
  // 確定後は内容が変わらないので長く持つ（今回の取得を確定版として保存し直す）
  $f = CACHE_DIR . '/' . "res_$rid" . '.html';
  if (is_file($f) && (time() - filemtime($f)) > TTL_DONE) { @touch($f); }
  $page = $result;
} else {
  $page = cached("card_$rid", TTL_LIVE, fn() => fetch_url("https://$host/race/shutuba.html?race_id=$rid"));
}

/* --- 抜き出し（軽い正規表現。DOM拡張が無い環境でも動くように） --- */
function pick(string $html, string $cls): string {
  if (preg_match('/class="[^"]*\b' . preg_quote($cls, '/') . '\b[^"]*"[^>]*>(.*?)</su', $html, $m)) {
    return trim(preg_replace('/\s+/u', ' ', strip_tags($m[1])));
  }
  return '';
}
/* netkeiba の無名条件戦 "C2111213(C212)" を「C2（十一）（十二）（十三）」に開く。
   ★同じ関数が core/race_app.js / index.html / race.html にもある。直すなら全部★ */
function prettyRaceName(string $name): string {
  $name = trim($name);
  if (!preg_match('/^([A-D][1-3]|\d+歳)(\d{4,})(?:\([^)]*\))?$/u', $name, $m)) return $name;
  if (strlen($m[2]) % 2) return $name;
  $groups = str_split($m[2], 2);
  $kdig = ['〇','一','二','三','四','五','六','七','八','九'];
  $k = function (int $n) use ($kdig): string {
    if ($n < 10) return $kdig[$n];
    if ($n < 20) return '十' . ($n > 10 ? $kdig[$n - 10] : '');
    return $kdig[intdiv($n, 10)] . '十' . ($n % 10 ? $kdig[$n % 10] : '');
  };
  $out = $m[1];
  foreach ($groups as $g) {
    $gi = (int)$g;
    if ($gi < 1 || $gi > 25) return $name;   // 想定外は触らない
    $out .= '（' . $k($gi) . '）';
  }
  return $out;
}
$raceName = prettyRaceName(pick($page, 'RaceName'));
$raceNum  = pick($page, 'RaceNum');
// 結果ページには RaceNum が無いことがある。rid の末尾2桁がR番号なので補う
if ($raceNum === '') { $raceNum = (int)substr($rid, 10, 2) . 'R'; }
$data01   = pick($page, 'RaceData01');
$data02   = pick($page, 'RaceData02');

/* 出走馬（結果ページ / 出馬表ページ どちらからも拾う） */
$rows = [];
// 結果ページは全 tr を見て、着順セルを持つ行だけ拾う（クラス名に頼らない）
$rowRe = $hasResult
  ? '/<tr[^>]*>((?:(?!<\/tr>).)*?class="Result_Num".*?)<\/tr>/su'
  : '/<tr[^>]*class="[^"]*HorseList[^"]*"[^>]*>(.*?)<\/tr>/su';
if (preg_match_all($rowRe, $page, $mm)) {
  foreach ($mm[1] as $tr) {
    // 馬名は db.netkeiba.com/horse/ へのリンク（父馬・調教師のリンクと紛れる）
    if (!preg_match('#db\.netkeiba\.com/horse/\d+[^>]*>\s*(?:<[^>]+>)*\s*([^<]+)#u', $tr, $hm)) continue;
    $name = trim($hm[1]);
    if ($name === '') continue;
    preg_match_all('/<td[^>]*>(.*?)<\/td>/su', $tr, $tds);
    $cell = function (int $i) use ($tds) {
      return isset($tds[1][$i])
        ? trim(preg_replace('/\s+/u', ' ', strip_tags($tds[1][$i]))) : '';
    };
    if ($hasResult) {
      $rows[] = ['rank' => $cell(0), 'waku' => $cell(1), 'uma' => $cell(2),
                 'name' => $name, 'jockey' => pick($tr, 'Jockey'), 'time' => $cell(7)];
    } else {
      $rows[] = ['rank' => '', 'waku' => $cell(0), 'uma' => $cell(1),
                 'name' => $name, 'jockey' => pick($tr, 'Jockey'), 'time' => ''];
    }
  }
}

/* 払戻（確定後のみ） */
$pays = [];
if ($hasResult && preg_match('/Payout_Detail_Table.*?<\/table>/su', $page, $pm)) {
  if (preg_match_all('/<tr[^>]*>(.*?)<\/tr>/su', $pm[0], $prs)) {
    foreach ($prs[1] as $tr) {
      if (!preg_match('/<th[^>]*>(.*?)<\/th>/su', $tr, $k)) continue;
      $kind = trim(strip_tags($k[1]));
      if (!preg_match('/class="Payout"[^>]*>(.*?)<\/td>/su', $tr, $p)) continue;
      $yen = trim(preg_replace('/\s+/u', ' ',
             strip_tags(preg_replace('/<br\s*\/?>/i', ' / ', $p[1]))));
      if ($kind !== '' && $yen !== '') $pays[] = [$kind, $yen];
    }
  }
}

$e = fn($s) => htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');
$title = trim(($raceNum ? "$raceNum " : '') . ($raceName ?: 'レース'));
$where = trim("$data01 $data02");
$isNar = !$isJra;
$kind  = $isJra ? '中央競馬' : '地方競馬';

$desc = $hasResult
  ? "{$title}の結果と払戻。" . ($rows ? "1着 {$rows[0]['name']}。" : '')
  : "{$title}の出馬表。" . ($rows ? count($rows) . '頭。' : '');
$desc .= " {$where}";

header('Content-Type: text/html; charset=UTF-8');
header('Cache-Control: public, max-age=120');
?>
<!doctype html>
<html lang="ja">
<meta charset="utf-8">
<title><?= $e($title) ?>｜<?= $e($kind) ?>の出馬表・結果 — カジ競馬</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="<?= $e(mb_substr($desc, 0, 120)) ?>">
<link rel="canonical" href="https://kajikeiba.com/race/<?= $e($rid) ?>/">
<meta property="og:type" content="article">
<meta property="og:title" content="<?= $e($title) ?>｜出馬表・結果">
<meta property="og:description" content="<?= $e(mb_substr($desc, 0, 120)) ?>">
<meta property="og:url" content="https://kajikeiba.com/race/<?= $e($rid) ?>/">
<meta property="og:image" content="https://kajikeiba.com/data/ogp.png">
<meta name="twitter:card" content="summary_large_image">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2591053009962162" crossorigin="anonymous"></script>
<?php
/* ★JSにも中身のハッシュを付ける★
   付けていなかったので、人格の定義を直しても端末が古いJSを使い続け、
   直したはずの印が画面では変わらない、という状態になっていた
   （theme.css で一度踏んだのと同じ穴を JS で繰り返していた）。
   PHPなので配信時に計算できる。生成し直す手間もズレも無い。 */
/* ★パスを文字列 "/core/..." で書かない★
   /lab/ 向けデプロイは "/core/" を "/lab/core/" に一括で書き換える。
   ディスク上の位置にそれを混ぜると __DIR__."/lab/core/..." になり
   ファイルが見つからずハッシュが付かなくなる。src属性側だけ書き換えさせる。 */
function av(string $file): string {
  $p = __DIR__ . DIRECTORY_SEPARATOR . 'core' . DIRECTORY_SEPARATOR . $file;
  return is_file($p) ? '?v=' . substr(md5_file($p), 0, 8) : '';
}
?>
<link rel="stylesheet" href="/core/theme.css<?= av('theme.css') ?>">
<script src="/core/theme.js<?= av('theme.js') ?>"></script>
<script src="/core/table.js<?= av('table.js') ?>" defer></script>
<link rel="stylesheet" href="/core/race.css<?= av('race.css') ?>">
<?php /* サーバー側HTMLは「中身のある土台」。JSが動けば差し替える。
         ★JSでのリダイレクトはしない★ URLが分かれると検索評価が割れるうえ、
         クローラにはリダイレクト、人には別ページという状態になりかねない。 */ ?>
<header><div class="hbar">
  <a class="logo" href="/">カジ<span>競馬</span></a>
  <div style="flex:1"></div>
  <button class="themebtn" type="button" style="margin-right:10px">☾</button>
  <a href="/" style="text-decoration:none">← レース一覧</a>
</div></header>
<div class="wrap">
<div id="ssr">
  <h1><?= $e($title) ?></h1>
  <p><?= $e($where) ?></p>
  <?php
  /* ★重賞なら過去データへ誘導★ ただし jusho の集計にレース名が
     完全一致したときだけリンクする（一致しなければ404を出さない）。
     レース名は "11R レース名" 形式なので R番号を落として突き合わせる。 */
  $jname = trim(preg_replace('/^\d+R\s*/u', '', $title));
  static $jusho_keys = null;
  if ($jusho_keys === null) {
    $jusho_keys = [];
    $jf = @file_get_contents(__DIR__ . '/data/jusho/data.json');
    if ($jf !== false) {
      $jj = json_decode($jf, true);
      if (is_array($jj)) { $jusho_keys = array_fill_keys(array_keys($jj), true); }
    }
  }
  if ($jname !== '' && isset($jusho_keys[$jname])):
  ?>
    <p style="margin:4px 0 12px"><a href="/data/jusho/?r=<?= rawurlencode($jname) ?>"
       style="display:inline-block;border:1px solid var(--line);border-radius:8px;
       padding:6px 12px;text-decoration:none">📊 <?= $e($jname) ?>の過去データ（人気・枠・脚質）</a></p>
  <?php endif ?>
  <?php if ($rows): ?>
  <table>
    <tr>
      <?php if ($hasResult): ?><th>着順</th><?php endif ?>
      <th>枠</th><th>馬番</th><th>馬名</th><th>騎手</th>
      <?php if ($hasResult): ?><th>タイム</th><?php endif ?>
    </tr>
    <?php foreach ($rows as $r): ?>
    <tr>
      <?php if ($hasResult): ?><td><?= $e($r['rank']) ?></td><?php endif ?>
      <td><?= $e($r['waku']) ?></td><td><?= $e($r['uma']) ?></td>
      <td><?= $e($r['name']) ?></td><td><?= $e($r['jockey']) ?></td>
      <?php if ($hasResult): ?><td><?= $e($r['time']) ?></td><?php endif ?>
    </tr>
    <?php endforeach ?>
  </table>
  <?php else: ?>
  <p>出馬表はまだ公開されていません。</p>
  <?php endif ?>

  <?php if ($pays): ?>
  <h2>払戻</h2>
  <table>
    <tr><th>券種</th><th>払戻</th></tr>
    <?php foreach ($pays as $p): ?>
    <tr><td><?= $e($p[0]) ?></td><td><?= $e($p[1]) ?></td></tr>
    <?php endforeach ?>
  </table>
  <?php endif ?>
  <p><a href="/">レース一覧へ</a></p>
</div>

<?php /* ここから動的版。JSが動かない環境では上の #ssr がそのまま残る。 */ ?>
<div class="vtabs" id="vtabs"></div>
<div class="rtabs" id="rtabs"></div>
<h1 id="title" style="display:none"></h1>
<p class="sub" id="sub"></p>
<div class="tabs" role="group" aria-label="表示の切替">
  <button id="tCard" aria-pressed="true">出馬表</button>
  <button id="tAi" aria-pressed="false">AI予想</button>
  <button id="tResult" aria-pressed="false">結果・払戻</button>
</div>
<div id="out"></div>
<footer>データ出典: netkeiba.com<br>
本ページは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a></footer>
</div>
<script src="/core/scoring.js<?= av('scoring.js') ?>"></script>
<script src="/core/ltr_model.js<?= av('ltr_model.js') ?>"></script>
<script src="/core/personas.js<?= av('personas.js') ?>"></script>
<script src="/core/netkeiba_past.js<?= av('netkeiba_past.js') ?>"></script>
<script src="/core/montecarlo.js<?= av('montecarlo.js') ?>"></script>
<script src="/core/race_app.js<?= av('race_app.js') ?>"></script>
<script>
/* アクセス計測（Cookieなし・自前）。失敗しても本体に影響させない */
try{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }catch(e){}
</script>

</html>
