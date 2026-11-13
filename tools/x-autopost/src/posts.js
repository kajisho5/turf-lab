/* 投稿の組み立て（Xには触らない。試験しやすいようにここだけ分けてある）
   2026-11-13: Xが1件の投稿に付けられる画像を4枚→20枚に増やしたので、まず1件にまとめて出す。
   1件で出せなかった時のために、今までどおり4枚ずつ分けた形（スレッド）も一緒に作る。 */
export const MAX_MEDIA = 20;      // 1件にまとめる時の上限
export const THREAD_MEDIA = 4;    // 分けて出す時の1件あたり

/* __autoOut → 分けて出す形 posts[{text, images[dataURL]}]（今までの形） */
export function toThread(kind, mode, out, caption) {
  const md = out.date && out.date.length === 8 ? `${+out.date.slice(4, 6)}/${+out.date.slice(6, 8)}` : out.date;
  const modeLbl = mode === "nar" ? "地方競馬" : "中央競馬";
  if (kind === "morning") {
    // 1枚目は「今日の★勝負」（★勝負が0の日は無い）。2枚目から場ごとのカード
    const imgs = [out.summary && out.summary.image].concat((out.cards || []).map(c => c.image)).filter(Boolean);
    const posts = [];
    for (let i = 0; i < imgs.length; i += THREAD_MEDIA) {
      // 文: 手で指定した文 → ページが作った文（数字を先頭にした形）→ それも無ければ昔の文
      posts.push({ text: caption || out.caption || `${md}\n${modeLbl}の予想です`, images: imgs.slice(i, i + THREAD_MEDIA) });
    }
    return posts;
  }
  // evening: tweet.html が posts[{text, images[]}] を4枚ずつに分けて用意している
  return (out.posts || []).map(p => ({ text: p.text || "", images: (p.images || []).filter(Boolean) }));
}

/* 分けて出す形 → 1件にまとめた形。まとめる意味が無い（もともと1件）・画像が20枚を超える時は null。
   文は「画像なしの投稿の文」をつなぐ（的中まとめ・段階別成績）。画像つき投稿の文（回収率です／答え合わせです）は
   画像の見出しなので落とす。文だけの投稿が1つも無ければ、最初の投稿の文を使う（朝の予想はこちら）。 */
export function mergePosts(posts, caption) {
  if (!posts || posts.length < 2) return null;
  const images = [];
  posts.forEach(p => (p.images || []).forEach(i => images.push(i)));
  if (!images.length || images.length > MAX_MEDIA) return null;
  const texts = posts.filter(p => !(p.images || []).length && p.text).map(p => p.text);
  // caption＝ページが作った1件用の文（夜の回）。あればそれを使う。無ければ今までどおり文をつないで整える
  const text = caption ? String(caption) : texts.length ? tidyMerged(texts) : (posts[0].text || "");
  return { text, images };
}

/* いくつかの文を1件の文に整える（2026-11-13・本人の指摘「タグが二つとかになってる」）。
   - ハッシュタグの行は集めて、重なりを除いて最後に1回だけ
   - 「▼朝の予想の答え合わせ」は外す（返信でぶら下げていた頃の見出し。今は単独の投稿）
   - 見出し【M/D 結果】は【M/D 答え合わせ】に。2つ目からの見出し【M/D ○○】は日付を繰り返さず「▼○○」に
   - 券種の前の◎（◎3連単 など＝◎を軸にした買い方の印）は外す。「◎4 ◎3連単」と◎が続いて読みにくいため
   数字や的中の行そのものは変えない */
export function tidyMerged(texts) {
  const tags = [], blocks = []; let seenHead = false;
  (texts || []).forEach(t => {
    const lines = [];
    String(t || "").split("\n").forEach(raw => {
      let l = raw.trim(); if (!l) return;
      if (/^(#\S+\s*)+$/.test(l)) { l.split(/\s+/).forEach(g => { if (g && !tags.includes(g)) tags.push(g); }); return; }
      if (l === "▼朝の予想の答え合わせ") return;
      const h = l.match(/^【(\d{1,2}\/\d{1,2}) (.+?)】(.*)$/);
      if (h) {
        if (!seenHead) { seenHead = true; l = `【${h[1]} ${h[2] === "結果" ? "答え合わせ" : h[2]}】${h[3]}`; }
        else l = "▼" + (h[2] === "段階別成績" ? "区分ごとの成績" : h[2]);
      }
      l = l.replace(/ ◎(?=(単勝|複勝|枠連|馬連|馬単|ワイド|3連複|3連単))/g, " ");
      lines.push(l);
    });
    if (lines.length) blocks.push(lines.join("\n"));
  });
  return blocks.join("\n\n") + (tags.length ? "\n\n" + tags.join(" ") : "");
}
