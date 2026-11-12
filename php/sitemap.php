<?php
/* sitemap.xml — 検索エンジンにレースページの存在を知らせる
 *
 * ★なぜ要るか★
 *   レースページはトップからしかリンクされておらず、しかも当日ぶんしか出ていない。
 *   放っておくと過去のレースページが一切見つけてもらえない。
 *   1日36〜80レース×365日ぶんが検索資産になるかどうかがここで決まる。
 *
 * ★作り方★
 *   netkeiba の日別一覧から race_id を取り、直近 DAYS 日ぶんを列挙する。
 *   毎回取りに行くと重いので1日キャッシュする。
 */
const DAYS  = 30;                     // 直近何日ぶんを載せるか
const CACHE = __DIR__ . '/cache/sitemap.xml';
const TTL   = 43200;                  // 12時間

header('Content-Type: application/xml; charset=UTF-8');

if (is_file(CACHE) && (time() - filemtime(CACHE)) < TTL) {
  readfile(CACHE);
  exit;
}

function fetch_url(string $url): string {
  $ch = curl_init($url);
  curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true, CURLOPT_FOLLOWLOCATION => true,
    CURLOPT_TIMEOUT => 15, CURLOPT_CONNECTTIMEOUT => 8, CURLOPT_ENCODING => '',
    CURLOPT_USERAGENT => 'Mozilla/5.0 (compatible; kajikeiba sitemap)',
  ]);
  $b = curl_exec($ch); curl_close($ch);
  return is_string($b) ? $b : '';
}

/* ★静的ページの一覧は自動生成★
   以前ここは手書きの配列だった。ページを作るたびに足す運用だったが、
   実際には足し忘れ、**公開済み37ページがsitemapに載っていなかった**
   （/db/combo/ /db/trainer-homeaway/ /data/waku/ など）。
   backtest/gen_sitemap_urls.py が PUBLIC_MAP から sitemap_urls.php を作るので、
   ページを増やしたら deploy.py を通すだけで反映される。 */
$urls = @include __DIR__ . '/sitemap_urls.php';
if (!is_array($urls) || !$urls) {
  // 生成物が無くても最低限は出す（トップだけ空、は避ける）
  $urls = [
    ['https://kajikeiba.com/',          'hourly',  '1.0'],
    ['https://kajikeiba.com/ai/',       'weekly',  '0.9'],
    ['https://kajikeiba.com/record/',   'daily',   '0.9'],
    ['https://kajikeiba.com/articles/', 'weekly',  '0.9'],
    ['https://kajikeiba.com/about/',    'monthly', '0.5'],
    ['https://kajikeiba.com/privacy/',  'yearly',  '0.3'],
  ];
}

/* ★重賞データ143レースを個別に載せる★
   /data/jusho/?r=レース名 は検索需要が大きいので1本ずつ sitemap に出す。
   data.json のキー（レース名）から動的に生成する。 */
$jusho = @file_get_contents(__DIR__ . '/data/jusho/data.json');
if ($jusho !== false) {
  $j = json_decode($jusho, true);
  if (is_array($j)) {
    foreach (array_keys($j) as $name) {
      $urls[] = ['https://kajikeiba.com/data/jusho/?r=' . rawurlencode($name),
                 'weekly', '0.7'];
    }
  }
}

$seen = [];
for ($i = 0; $i < DAYS; $i++) {
  $d = date('Ymd', strtotime("-$i day"));
  foreach (['race.netkeiba.com', 'nar.netkeiba.com'] as $host) {
    $html = fetch_url("https://$host/top/race_list_sub.html?kaisai_date=$d");
    if ($html === '') continue;
    if (preg_match_all('/race_id=(\d{12})/', $html, $m)) {
      foreach ($m[1] as $rid) {
        if (isset($seen[$rid])) continue;
        $seen[$rid] = true;
        // 当日は変わるので hourly、過去は確定しているので monthly
        $urls[] = ["https://kajikeiba.com/race/$rid/", $i === 0 ? 'hourly' : 'monthly',
                   $i === 0 ? '0.9' : '0.6'];
      }
    }
  }
}

$xml = '<?xml version="1.0" encoding="UTF-8"?>' . "\n"
     . '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' . "\n";
foreach ($urls as [$loc, $freq, $pri]) {
  $xml .= "<url><loc>" . htmlspecialchars($loc, ENT_XML1)
        . "</loc><changefreq>$freq</changefreq><priority>$pri</priority></url>\n";
}
$xml .= "</urlset>\n";

if (!is_dir(dirname(CACHE))) { @mkdir(dirname(CACHE), 0755, true); }
@file_put_contents(CACHE, $xml, LOCK_EX);
echo $xml;
