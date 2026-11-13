const {chromium}=require('playwright'); const fs=require('fs');
(async()=>{ const b=await chromium.launch({proxy:{server:process.env.HTTPS_PROXY}});
  for(const n of ['f1_battle','f2_track','f3_check','f4_recovery','f5_weekly']){ const svg=fs.readFileSync(__dirname+'/'+n+'.svg','utf8');
    const m=/width="(\d+)" height="(\d+)"/.exec(svg); const p=await b.newPage({viewport:{width:+m[1],height:+m[2]},deviceScaleFactor:1});
    await p.setContent('<html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Noto+Serif+JP:wght@700;900&family=Roboto+Condensed:wght@400;700&display=block"><style>body{margin:0}</style></head><body>'+svg+'</body></html>',{waitUntil:'networkidle',timeout:60000});
    await p.evaluate(()=>document.fonts.ready); await p.waitForTimeout(800); await p.screenshot({path:__dirname+'/'+n+'.png'}); await p.close(); console.log(n,m[1],m[2]); }
  await b.close(); })();
