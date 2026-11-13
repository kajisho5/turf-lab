const {chromium}=require('playwright'); const fs=require('fs');
(async()=>{ const b=await chromium.launch({proxy:{server:process.env.HTTPS_PROXY}});
  for(const f of fs.readdirSync(__dirname).filter(x=>x.endsWith('.svg'))){ const svg=fs.readFileSync(__dirname+'/'+f,'utf8');
    const m=/width="(\d+)" height="(\d+)"/.exec(svg); const p=await b.newPage({viewport:{width:+m[1],height:+m[2]},deviceScaleFactor:1});
    await p.setContent('<html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Noto+Serif+JP:wght@700;900&family=Roboto+Condensed:wght@400;700&display=block"><style>body{margin:0}</style></head><body>'+svg+'</body></html>',{waitUntil:'networkidle',timeout:60000});
    await p.evaluate(()=>document.fonts.ready); await p.waitForTimeout(600); await p.screenshot({path:__dirname+'/'+f.replace('.svg','.png')}); await p.close(); }
  await b.close(); })();
