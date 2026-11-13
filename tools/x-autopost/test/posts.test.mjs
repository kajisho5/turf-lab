import { toThread, mergePosts } from "../src/posts.js";
let ok=0, ng=0; const eq=(n,a,b)=>{ const r=JSON.stringify(a)===JSON.stringify(b); r?ok++:(ng++,console.log("NG",n,JSON.stringify(a),JSON.stringify(b))); };
const img=n=>Array.from({length:n},(_,i)=>"data:image/png;base64,otter"+i);
// 朝: 4場 → もともと1件（まとめ不要）
let t=toThread("morning","nar",{date:"20261114",cards:img(4).map(image=>({image}))});
eq("朝4場は1件",t.length,1); eq("朝4場まとめ不要",mergePosts(t),null); eq("朝の文",t[0].text,"11/14\n地方競馬の予想です");
// 朝: 6場 → 分けると2件、まとめると1件6枚
t=toThread("morning","nar",{date:"20261114",cards:img(6).map(image=>({image}))});
eq("朝6場は分けると2件",t.map(p=>p.images.length),[4,2]); let m=mergePosts(t); eq("朝6場まとめ",[m.text,m.images.length],["11/14\n地方競馬の予想です",6]);
eq("画像の順番",m.images,img(6));
// 夜: 文・画像3・文・画像4+2
const ev={posts:[{text:"的中まとめ",images:[]},{text:"回収率です",images:img(3)},{text:"段階別",images:[]},{text:"答え合わせです",images:img(4)},{text:"答え合わせです（2）",images:img(2)}]};
t=toThread("evening","nar",ev); eq("夜は分けると5件",t.length,5); m=mergePosts(t);
eq("夜まとめの文",m.text,"的中まとめ\n\n段階別"); eq("夜まとめの画像",m.images.length,9);
// 21枚以上はまとめない
eq("21枚はまとめない",mergePosts([{text:"a",images:img(11)},{text:"b",images:img(10)}]),null);
// 文だけ → まとめない（画像が無い）
eq("文だけはまとめない",mergePosts([{text:"a",images:[]},{text:"b",images:[]}]),null);
console.log("OK",ok,"NG",ng); process.exit(ng?1:0);
