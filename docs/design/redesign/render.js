const {chromium}=require('playwright'); const fs=require('fs');
(async()=>{ const b=await chromium.launch({proxy:{server:process.env.HTTPS_PROXY}});
  for(const n of ['a','b','c','d','e','f']){ const p=await b.newPage({viewport:{width:1240,height:1710},deviceScaleFactor:1});
    const svg=fs.readFileSync(__dirname+'/'+n+'.svg','utf8');
    await p.setContent('<html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Noto+Serif+JP:wght@700;900&family=Roboto+Condensed:wght@400;700&family=Chakra+Petch:wght@500;700&family=Saira+Condensed:wght@500;700&display=block"><style>body{margin:0}</style></head><body>'+svg+'</body></html>',{waitUntil:'networkidle',timeout:60000});
    await p.evaluate(()=>document.fonts.ready); await p.waitForTimeout(800);
    console.log(n, await p.evaluate(()=>[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family).filter((v,i,a)=>a.indexOf(v)===i).join(',')));
    await p.screenshot({path:__dirname+'/'+n+'.png'}); await p.close(); }
  await b.close(); })();
