/* テーマ切り替え（ライト基本 / ダーク選択制）
 *
 * ★描画前に適用する★
 *   body の後で切り替えると、ダークを選んでいる人に一瞬ライトが見える（チラつき）。
 *   このファイルは <head> 相当の位置で同期読み込みし、最初の描画前に属性を立てる。
 *
 * ★端末のダーク設定には自動追従しない★
 *   記事の図やOGP画像が明色前提。意図しない見え方を避けるため、
 *   本人が押すまではライトのままにする。
 */
/* ===== エラー監視（kajikeiba.com限定） =====
   ★なぜここに置くか★ theme.jsは全ページ(101ファイル)が読む唯一の共通スクリプトなので、
   ここに足せばコピーを増やさず全公開ページへ効く（tweet.html側は別途inline実装済み）。
   ★kajikeiba.com限定★ 知人向けの別サイトには error_log.php を配っていないため、
   そこでは何もしない（404を無駄に叩かない）。 */
(function () {
  if (location.hostname !== 'kajikeiba.com') return;
  var sent = 0;
  var MAX = 5;
  function report(msg, stack) {
    if (sent >= MAX) return;
    sent++;
    try {
      fetch('/error_log.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page: location.pathname,
          msg: String(msg == null ? '' : msg).slice(0, 500),
          stack: String(stack == null ? '' : stack).slice(0, 2000)
        }),
        keepalive: true
      }).catch(function () {});
    } catch (e) {}
  }
  window.addEventListener('error', function (e) {
    report(e.message, e.error && e.error.stack);
  });
  window.addEventListener('unhandledrejection', function (e) {
    var r = e.reason;
    report('unhandledrejection: ' + (r && r.message ? r.message : r), r && r.stack);
  });
})();

(function () {
  var KEY = 'kk_theme';
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (saved === 'dark') document.documentElement.setAttribute('data-theme', 'dark');

  window.kkTheme = {
    toggle: function () {
      var el = document.documentElement;
      var dark = el.getAttribute('data-theme') === 'dark';
      if (dark) el.removeAttribute('data-theme');
      else el.setAttribute('data-theme', 'dark');
      try { localStorage.setItem(KEY, dark ? 'light' : 'dark'); } catch (e) {}
      window.kkTheme.paint();
    },
    /* ボタンの見た目を今の状態に合わせる */
    paint: function () {
      var dark = document.documentElement.getAttribute('data-theme') === 'dark';
      document.querySelectorAll('.themebtn').forEach(function (b) {
        b.textContent = dark ? '☀' : '☾';
        b.setAttribute('aria-label', dark ? 'ライトモードに切り替え' : 'ダークモードに切り替え');
        b.title = b.getAttribute('aria-label');
      });
    },
    /* 全ページ共通の初期化。ボタンが無ければ何もしない */
    init: function () {
      document.querySelectorAll('.themebtn').forEach(function (b) {
        b.onclick = window.kkTheme.toggle;
      });
      window.kkTheme.paint();
      window.kkTheme.bottomNav();
      window.kkTheme.legalNote();
    },

    /* ★全ページ共通の法務注意書き（2026-07-26追加）★
       競馬（公営ギャンブル）予想サイトの公開にあたり、20歳未満の馬券購入禁止と
       ギャンブル等依存症の相談窓口を全ページで明示する。全ページが theme.js を
       読むので、bottomNav と同じくここで1回差し込めば全ページに出る。
       相談先は実在する公式窓口のみ（依存症対策全国センター／厚生労働省）。
       data-nolegal の付いたページ（運営用tweet.html等）には出さない。 */
    legalNote: function () {
      if (document.getElementById('kklegal')) return;
      if (document.body.hasAttribute('data-nolegal')) return;
      var d = document.createElement('div');
      d.id = 'kklegal';
      d.innerHTML =
        '<strong>馬券が買えるのは20歳から。</strong>20歳未満の購入は法律で禁止されています。'
        + '　ギャンブルは無理のない範囲で。やめたくてもやめられないと感じたら'
        + '<a href="https://www.ncasa-japan.jp/you-do/treatment/treatment-map/" target="_blank" rel="noopener">全国の相談窓口</a>'
        + '（<a href="https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000149274.html" target="_blank" rel="noopener">厚労省の案内</a>）へ。';
      document.body.appendChild(d);
      if (!document.getElementById('kklegal-css')) {
        var s = document.createElement('style');
        s.id = 'kklegal-css';
        s.textContent =
          '#kklegal{max-width:960px;margin:32px auto 0;padding:12px 16px;'
          + 'border-top:1px solid var(--line,#ddd);color:var(--mute,#888);'
          + 'font-size:14px;line-height:1.7;text-align:center}'   /* 14px未満禁止(DADS・フッターは14px枠) */
          + '#kklegal a{color:var(--blue,#2b6cb0)}'
          + '#kklegal strong{color:var(--txt,#222)}'
          + '@media (max-width:1024px){#kklegal{margin-bottom:calc(58px + env(safe-area-inset-bottom))}}';
        document.head.appendChild(s);
      }
    },

    /* ★スマホ/タブレット用の下部ナビ（アプリ風）★
       全ページが theme.js を読むので、ここで1回だけ差し込めば全ページに出る。
       広い画面（PC）では上部ナビで足りるので隠す。data-nonav の付いたページは出さない。
       ★lab へは href の "/xxx" が deploy 時に "/lab/xxx" へ書き換えられる（ai/等は対象）★ */
    bottomNav: function () {
      if (document.getElementById('kkbn')) return;
      if (document.body.hasAttribute('data-nonav')) return;
      /* ★base はここで実行時に決める★
         lab は /lab/ 配下。href を "/" と書くと lab_transform の対象外で
         書き換わらず、lab のホームがサイトのルートに飛んでいた（本番で発覚）。
         なので "ai/" 等の相対セグメントを base に足して組み立てる。 */
      var lab = location.pathname.indexOf('/lab/') === 0 || location.pathname === '/lab';
      var base = lab ? '/lab/' : '/';
      var items = [
        ['', 'レース', 'M3 10l9-7 9 7M5 9v11h5v-6h4v6h5V9'],
        ['ai/', 'AI予想', 'M4 19V5m5 14V9m5 10V4m5 15v-7'],
        ['record/', '記録', 'M9 5h6M5 5h.01M5 12h.01M5 19h.01M9 12h6M9 19h6'],
        ['articles/', '記事', 'M6 3h9l3 3v15H6zM9 8h6M9 12h6M9 16h4'],
        ['db/', 'データ', 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3']
      ];
      var path = location.pathname.replace(/^\/lab(\/|$)/, '/');   // 判定は素のパスで
      var nav = document.createElement('nav');
      nav.id = 'kkbn';
      nav.setAttribute('aria-label', 'メインメニュー');
      nav.innerHTML = items.map(function (it) {
        var seg = it[0], label = it[1], d = it[2];
        var active = seg === '' ? path === '/' : path.indexOf('/' + seg) === 0;
        return '<a href="' + base + seg + '"' + (active ? ' aria-current="page"' : '') + '>'
          + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"'
          + ' stroke-linecap="round" stroke-linejoin="round"><path d="' + d + '"/></svg>'
          + '<span>' + label + '</span></a>';
      }).join('');
      document.body.appendChild(nav);
      if (!document.getElementById('kkbn-css')) {
        var s = document.createElement('style');
        s.id = 'kkbn-css';
        s.textContent =
          '#kkbn{position:fixed;left:0;right:0;bottom:0;z-index:900;display:none;' +
          'grid-template-columns:repeat(5,1fr);background:var(--panel,#fff);' +
          'border-top:1px solid var(--line,#ddd);padding-bottom:env(safe-area-inset-bottom)}' +
          '#kkbn a{display:flex;flex-direction:column;align-items:center;gap:2px;' +
          // ★14px未満は禁止（DADS_DESIGN.md）★ 11pxだった。5列に14pxを収めるため
          //   左右paddingを詰め、はみ出す端末では文字を縮めず折り返さない指定にする。
          'padding:7px 1px 6px;text-decoration:none;color:var(--mute,#888);font-size:14px;' +
          'font-weight:700;white-space:nowrap;letter-spacing:-0.02em}' +
          '#kkbn a svg{width:23px;height:23px}' +
          '#kkbn a[aria-current="page"]{color:var(--blue,#2b6cb0)}' +
          '@media (max-width:1024px){#kkbn{display:grid}' +
          'body{padding-bottom:calc(58px + env(safe-area-inset-bottom))}}';
        document.head.appendChild(s);
      }
    }
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.kkTheme.init);
  } else {
    window.kkTheme.init();
  }
})();
