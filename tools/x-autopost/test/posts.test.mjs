import { toThread, mergePosts, tidyMerged } from "../src/posts.js";
let ok=0, ng=0; const eq=(n,a,b)=>{ const r=JSON.stringify(a)===JSON.stringify(b); r?ok++:(ng++,console.log("NG",n,JSON.stringify(a),JSON.stringify(b))); };
const img=n=>Array.from({length:n},(_,i)=>"data:image/png;base64,otter"+i);
// 朝: 4場 → もともと1件（まとめ不要）
let t=toThread("morning","nar",{date:"20261114",cards:img(4).map(image=>({image}))});
eq("朝4場は1件",t.length,1); eq("朝4場まとめ不要",mergePosts(t),null); eq("朝の文",t[0].text,"11/14\n地方競馬の予想です");
// 朝: 6場 → 分けると2件、まとめると1件6枚
t=toThread("morning","nar",{date:"20261114",cards:img(6).map(image=>({image}))});
eq("朝6場は分けると2件",t.map(p=>p.images.length),[4,2]); let m=mergePosts(t); eq("朝6場まとめ",[m.text,m.images.length],["11/14\n地方競馬の予想です",6]);
eq("画像の順番",m.images,img(6));
// 朝: 「今日の★勝負」が1枚目に入る（4場＋1枚＝5枚 → 分けると 4+1、まとめると5枚）
t=toThread("morning","nar",{date:"20261114",summary:{image:"data:image/png;base64,summary"},cards:img(4).map(image=>({image}))});
eq("まとめの1枚が先頭",t[0].images[0],"data:image/png;base64,summary"); eq("5枚は分けると2件",t.map(p=>p.images.length),[4,1]);
eq("5枚をまとめる",mergePosts(t).images.length,5);
eq("★勝負0の日は足さない",toThread("morning","nar",{date:"20261114",summary:null,cards:img(2).map(image=>({image}))})[0].images.length,2);
// 夜: 文・画像3・文・画像4+2
const ev={posts:[{text:"的中まとめ",images:[]},{text:"回収率です",images:img(3)},{text:"段階別",images:[]},{text:"答え合わせです",images:img(4)},{text:"答え合わせです（2）",images:img(2)}]};
t=toThread("evening","nar",ev); eq("夜は分けると5件",t.length,5); m=mergePosts(t);
eq("夜まとめの文",m.text,"的中まとめ\n\n段階別"); eq("夜まとめの画像",m.images.length,9);
// 1件にまとめた時の文（タグは最後に1回・見出しを整える・数字の行は変えない）
eq("文を整える", tidyMerged(["▼朝の予想の答え合わせ\n【11/14 結果】地方\n★潮見10R ◎1 ◎3連単 108,610円\n鳴瀬10R ◎4 ◎ワイド 680円\n当たりは出てる。\n#競馬予想 #地方競馬",
  "【11/14 段階別成績】地方\n全レース：41R 的中90% 回収115%\n★勝負：13R 的中100% 回収84%\n区分の並びはバラバラ。そのまま報告\n#競馬予想 #地方競馬"]),
  "【11/14 答え合わせ】地方\n★潮見10R ◎1 3連単 108,610円\n鳴瀬10R ◎4 ワイド 680円\n当たりは出てる。\n\n▼区分ごとの成績\n全レース：41R 的中90% 回収115%\n★勝負：13R 的中100% 回収84%\n区分の並びはバラバラ。そのまま報告\n\n#競馬予想 #地方競馬");
eq("タグが違えば両方残す（重なりだけ除く）", tidyMerged(["a\n#競馬予想 #地方競馬", "b\n#競馬予想 #競馬"]), "a\n\nb\n\n#競馬予想 #地方競馬 #競馬");
eq("タグが無ければ足さない", tidyMerged(["a", "b"]), "a\n\nb");
eq("文の中の # は動かさない", tidyMerged(["#1 の馬が勝った\n結果 #競馬予想 つき"]), "#1 の馬が勝った\n結果 #競馬予想 つき");
// 21枚以上はまとめない
eq("21枚はまとめない",mergePosts([{text:"a",images:img(11)},{text:"b",images:img(10)}]),null);
// 文だけ → まとめない（画像が無い）
eq("文だけはまとめない",mergePosts([{text:"a",images:[]},{text:"b",images:[]}]),null);
// 前の月（日本時間）。worker.js は puppeteer を読むのでここでは同じ式を確かめる
const prevMonth=(ms)=>{ const j=new Date(ms+9*3600e3); const d=new Date(Date.UTC(j.getUTCFullYear(),j.getUTCMonth()-1,1)); return `${d.getUTCFullYear()}${String(d.getUTCMonth()+1).padStart(2,"0")}`; };
eq("12/1 9:00 → 11月",prevMonth(Date.UTC(2026,11,1,0,0)),"202611"); eq("1/1 9:00 → 前年12月",prevMonth(Date.UTC(2027,0,1,0,0)),"202612");
console.log("OK",ok,"NG",ng); process.exit(ng?1:0);
