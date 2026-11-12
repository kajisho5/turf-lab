global.MODE="nar"; global.fetch=()=>Promise.reject(new Error("offline"));
const fs=require("fs"), readline=require("readline");
const E=require("./h3.js");
const file=process.argv[2], LIMIT=+(process.argv[3]||0);
(async()=>{
  const pays=JSON.parse(fs.readFileSync("/mnt/user-data/outputs/pays_fullhistory.json","utf8"));
  const rl=readline.createInterface({input:fs.createReadStream(file)});
  let n=0,hit=0,payN=0,ret=0,t0=Date.now();
  for await (const line of rl){
    if(LIMIT&&n>=LIMIT) break;
    let rec; try{ rec=JSON.parse(line); }catch(_){ continue; }
    E.setPS({entries:rec.entries, cond:rec.cond, scratched:[]});
    const r=await E.scoreRace("X",{no:rec.no,race_id:rec.rid,name:rec.cond.raceName},rec.track).catch(()=>null);
    if(!r||!r.ranked||r.skip||!r.ranked.length) continue;
    const ax=String(r.ranked[0].num);
    const rk=rec.ranks[ax];
    if(rk==null) continue;
    n++;
    if(rk<=3) hit++;
    const pay=pays[rec.rid];
    if(pay&&pay.fuku){ payN++; if(pay.fuku[ax]!=null) ret+=pay.fuku[ax]; }
  }
  const dt=(Date.now()-t0)/1000;
  console.log(`${file.split("/").pop()}: ${n}R 複勝率${(100*hit/n).toFixed(2)}% 複ROI${payN?(100*ret/(payN*100)).toFixed(0):"-"}%(${payN}R) ${(n/dt).toFixed(0)}R/s`);
})();
