/* 表の並べ替え — 全ページ共通
 *
 * ★1か所に置く理由★
 *   リーディングも馬検索も記事の表も、同じ「押したら並び替わる」が欲しい。
 *   ページごとに書くと、挙動が微妙に食い違ううえ直す場所が増える。
 *   色（縞・ホバー）は core/theme.css 側、動きはこのファイル。
 *
 * ★使い方★
 *   <table class="zebra sortable"> と書けば、勝手に全列が押せるようになる。
 *   並べ替えたくない列は <th data-nosort> を付ける。
 *
 * ★数値の判定★
 *   "1,234" "68%" "104%" "—" が混ざる。カンマと%を外して数値化し、
 *   数値にならないものは文字列として比較する。
 *   ★空欄・「—」は常に最後に置く★ 昇順で先頭に来ると
 *   「データが無い行が最良」に見えてしまう。
 *
 * ★縞は並べ替え後も1行おきに保つ★
 *   CSSの nth-child は DOM順で効くので、行を並べ替えれば自動で付き直る。
 */
(function () {
  'use strict';

  function cellValue(tr, i) {
    const td = tr.children[i];
    return td ? td.textContent.trim() : '';
  }

  function toNum(s) {
    if (!s) return null;
    const t = s.replace(/[,%\s円]/g, '')
               .replace(/^＋|^\+/, '')
               .replace(/^−|^-/, '-');
    if (t === '' || t === '—' || t === '―') return null;
    const v = Number(t);
    return Number.isFinite(v) ? v : null;
  }

  function sortTable(table, colIndex, dir) {
    const tbody = table.tBodies[0] || table;
    // ヘッダ行が tbody に混ざっている表があるので、th を含む行は動かさない
    const rows = [...tbody.rows].filter(r => !r.querySelector('th'));
    const fixed = [...tbody.rows].filter(r => r.querySelector('th'));

    const decorated = rows.map((tr, idx) => {
      const raw = cellValue(tr, colIndex);
      return { tr, idx, raw, num: toNum(raw) };
    });
    const anyNum = decorated.some(d => d.num !== null);

    decorated.sort((a, b) => {
      // 値なしは常に最後（昇順で先頭に来ると「無い行が最良」に見える）
      const ae = a.raw === '' || a.raw === '—' || a.raw === '―';
      const be = b.raw === '' || b.raw === '—' || b.raw === '―';
      if (ae !== be) return ae ? 1 : -1;
      let c;
      if (anyNum) {
        const av = a.num === null ? -Infinity : a.num;
        const bv = b.num === null ? -Infinity : b.num;
        c = av - bv;
      } else {
        c = a.raw.localeCompare(b.raw, 'ja');
      }
      if (c === 0) return a.idx - b.idx;    // 同値は元の順を保つ（安定ソート）
      return dir === 'asc' ? c : -c;
    });

    const frag = document.createDocumentFragment();
    fixed.forEach(r => frag.appendChild(r));
    decorated.forEach(d => frag.appendChild(d.tr));
    tbody.appendChild(frag);
  }

  function setup(table) {
    const head = table.tHead ? table.tHead.rows[0] : table.rows[0];
    if (!head) return;
    [...head.cells].forEach((th, i) => {
      if (th.hasAttribute('data-nosort')) return;
      th.classList.add('sortable');
      th.setAttribute('tabindex', '0');
      th.setAttribute('role', 'button');
      const run = () => {
        const cur = th.getAttribute('aria-sort');
        // 数値の列は「大きい順」から始めたい（複勝率が高い順に見たい、が普通）
        const first = /率|%|回収|勝利|出走|騎乗|数|順/.test(th.textContent) ? 'desc' : 'asc';
        const dir = cur === 'descending' ? 'asc'
                  : cur === 'ascending' ? 'desc' : first;
        [...head.cells].forEach(o => o.removeAttribute('aria-sort'));
        th.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending');
        sortTable(table, i, dir);
      };
      th.addEventListener('click', run);
      th.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); run(); }
      });
    });
  }

  function init() {
    document.querySelectorAll('table.sortable').forEach(setup);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  window.kkTable = { setup, sortTable };
})();
