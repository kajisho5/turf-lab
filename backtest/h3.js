const fs=require("fs");
const mk=(over)=>new Proxy(function(){},{ get:(t,p)=>{ if(over&&p in over)return over[p];
  if(p==="value"||p==="textContent"||p==="innerHTML"||p==="innerText")return "";
  if(p==="classList")return {toggle:()=>{},add:()=>{},remove:()=>{},contains:()=>false};
  if(p==="style")return mk(); if(p==="length")return 0; if(p==="dataset")return {};
  if(p===Symbol.iterator)return function*(){}(); if(p==="checked")return false; return mk(); },
  apply:()=>mk(), set:()=>true });
const dummy=mk();
const els={ localAffChk:{checked:false}, noOddsFinal:{checked:true}, mode:{value:"nar"}, date:{value:"20260610"} };
global.document={getElementById:(id)=>els[id]||dummy,querySelector:(s)=>{const id=(s||"").replace("#","");return els[id]||dummy;},querySelectorAll:()=>[],
  addEventListener:()=>{},createElement:()=>dummy,body:dummy,documentElement:dummy,head:dummy};
global.window=global; global.addEventListener=()=>{};
global.matchMedia=()=>({matches:false,addEventListener:()=>{},addListener:()=>{}});
global.localStorage={getItem:()=>null,setItem:()=>{},removeItem:()=>{},clear:()=>{}};
global.MutationObserver=class{observe(){}disconnect(){}};
global.navigator={userAgent:"node"};
global.location={search:"",href:"",hostname:"localhost"};
const _fetch=global.fetch;
global.fetch=(url,opt)=>{ if(typeof url==="string" && !/^https?:/.test(url)) url="https://seventh-well.com/odds/"+url; return _fetch(url,opt); };
let sc=fs.readFileSync("script.js","utf8");
if(process.env.KILL){
  const kills=process.env.KILL.split(",");
  sc=sc.split("\n").map(line=>{
    for(const k of kills){
      const tag="__T('"+k+"',";
      const at=line.indexOf(tag);
      if(at<0) continue;
      // __T('名前', ... ) の閉じ括弧を対応付けて探す
      let i=at+tag.length, depth=1;
      while(i<line.length && depth>0){
        if(line[i]==="(") depth++;
        else if(line[i]===")") depth--;
        if(depth===0) break;
        i++;
      }
      line = line.slice(0,at+tag.length) + "0" + line.slice(i);
    }
    return line;
  }).join("\n");
}

// SCALE=因子:倍率,因子:倍率 … その因子の寄与を ×倍率 する（重みスイープ用）。KILLの掛け算版。
if(process.env.SCALE){
  const scales=process.env.SCALE.split(",").map(s=>{const j=s.lastIndexOf(":");return [s.slice(0,j), s.slice(j+1)];});
  sc=sc.split("\n").map(line=>{
    for(const [k,mult] of scales){
      const tag="__T('"+k+"',";
      const at=line.indexOf(tag);
      if(at<0) continue;
      let i=at+tag.length, depth=1;
      while(i<line.length && depth>0){
        if(line[i]==="(") depth++;
        else if(line[i]===")") depth--;
        if(depth===0) break;
        i++;
      }
      const val=line.slice(at+tag.length, i);
      line = line.slice(0,at+tag.length) + "("+val+")*"+mult + line.slice(i);
    }
    return line;
  }).join("\n");
}


if(process.env.NO_SIRE==="1"){
  sc=sc.replace("if(runs>=15) s+=__T('血統(馬場)'","if(false) s+=__T('血統(馬場)'");
  sc=sc.replace("if(ss[4]!=null && ss[4]>=1.5) s+=__T('血統(EI)'","if(false) s+=__T('血統(EI)'");
}
if(process.env.NO_STYLE==="1"){ sc=sc.replace('const STYLE_LIFT={ "逃":15.1, "先":4.6, "差":-2.9, "追":-9.9 };','const STYLE_LIFT={ "逃":0, "先":0, "差":0, "追":0 };'); }
sc+="\n;globalThis.__PS_OVERRIDE=null; parseShutuba=(function(_op){ return function(h){ return globalThis.__PS_OVERRIDE || _op(h); }; })(parseShutuba);\n;globalThis.__exp={scoreRace,setPS:function(p){globalThis.__PS_OVERRIDE=p;},parseShutuba,parseResult,fetchDecoded,shutubaURL,resultURL,setMode:function(m){try{MODE=m;}catch(_){}},fullBreakdown:(typeof fullBreakdown!=='undefined'?fullBreakdown:null),scoreBreakdown:(typeof scoreBreakdown!=='undefined'?scoreBreakdown:null),classLevelName:(typeof classLevelName!=='undefined'?classLevelName:null),factorW:(typeof factorW!=='undefined'?factorW:null),GBM_FEAT:(typeof GBM_MODEL!=='undefined'?GBM_MODEL.feat:null),gbmScore:(typeof gbmScore!=='undefined'?gbmScore:null),setField:function(n){globalThis.__FIELD__=n;}};\n";
try{ new Function(sc)(); }catch(e){ console.error("EVAL ERR:",e.message); }
module.exports=globalThis.__exp||{};
// ★過去レースのバックテストでは #date スタブが常に固定値("20260610")を返すため、
//   休養日数のような「今日の日付」依存の因子がレースの実日付を無視して常に
//   未来の固定日付との差分になり、実質「常に最大値」で発火してしまう
//   （2026-07-26発覚: 重賞休養factorのKILL A/Bテストで全馬に一律+3が付き
//   相対順位が変わらないというバグとして表面化した）。過去レース単位で
//   raceDateを差し替えられるようにする。
module.exports.setDate=function(d){ els.date.value=d; };
