const {chromium}=require('playwright'); const fs=require('fs');
(async()=>{ const b=await chromium.launch({proxy:{server:process.env.HTTPS_PROXY}});
  for(const f of fs.readdirSync(__dirname).filter(x=>/\.svg$/.test(x))){ const svg=fs.readFileSync(__dirname+'/'+f,'utf8');
    const m=/width="(\d+)" height="(\d+)"/.exec(svg); const p=await b.newPage({viewport:{width:+m[1],height:Math.ceil(+m[2])},deviceScaleFactor:1});
    await p.setContent('<html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Barlow+Condensed:wght@500;700&display=block"><style>body{margin:0;background:#000}</style></head><body>'+svg+'</body></html>',{waitUntil:'networkidle',timeout:90000});
    await p.evaluate(()=>document.fonts.ready); await p.waitForTimeout(800); await p.screenshot({path:__dirname+'/'+f.replace('.svg','.png')}); await p.close(); console.log(f,m[1],m[2]); }
  await b.close(); })();
