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
    const imgs = (out.cards || []).map(c => c.image).filter(Boolean);
    const posts = [];
    for (let i = 0; i < imgs.length; i += THREAD_MEDIA) {
      posts.push({ text: caption || `${md}\n${modeLbl}の予想です`, images: imgs.slice(i, i + THREAD_MEDIA) });
    }
    return posts;
  }
  // evening: tweet.html が posts[{text, images[]}] を4枚ずつに分けて用意している
  return (out.posts || []).map(p => ({ text: p.text || "", images: (p.images || []).filter(Boolean) }));
}

/* 分けて出す形 → 1件にまとめた形。まとめる意味が無い（もともと1件）・画像が20枚を超える時は null。
   文は「画像なしの投稿の文」をつなぐ（的中まとめ・段階別成績）。画像つき投稿の文（回収率です／答え合わせです）は
   画像の見出しなので落とす。文だけの投稿が1つも無ければ、最初の投稿の文を使う（朝の予想はこちら）。 */
export function mergePosts(posts) {
  if (!posts || posts.length < 2) return null;
  const images = [];
  posts.forEach(p => (p.images || []).forEach(i => images.push(i)));
  if (!images.length || images.length > MAX_MEDIA) return null;
  const texts = posts.filter(p => !(p.images || []).length && p.text).map(p => p.text);
  const text = texts.length ? texts.join("\n\n") : (posts[0].text || "");
  return { text, images };
}
