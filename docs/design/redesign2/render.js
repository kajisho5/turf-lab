const {chromium}=require('playwright'); const fs=require('fs');
const FONTS='family=Noto+Sans+JP:wght@400;500;700;900&family=Noto+Serif+JP:wght@700;900&family=Zen+Kaku+Gothic+New:wght@500;700;900&family=Barlow+Condensed:ital,wght@0,500;0,700;1,700&family=Shippori+Mincho+B1:wght@500;600;700;800&family=DotGothic16&family=Oswald:wght@500;600;700&family=M+PLUS+Rounded+1c:wght@500;700;800&family=Anton&family=Saira+Condensed:wght@500;700&family=Cormorant+Garamond:wght@500;600;700&family=Archivo+Black';
(async()=>{ const b=await chromium.launch({proxy:{server:process.env.HTTPS_PROXY}});
  for(const f of fs.readdirSync(__dirname).filter(x=>/^d\d+\.svg$/.test(x))){ const svg=fs.readFileSync(__dirname+'/'+f,'utf8');
    const m=/width="(\d+)" height="(\d+)"/.exec(svg); const p=await b.newPage({viewport:{width:+m[1],height:+m[2]},deviceScaleFactor:1});
    await p.setContent('<html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css2?'+FONTS+'&display=block"><style>body{margin:0;background:#000}</style></head><body>'+svg+'</body></html>',{waitUntil:'networkidle',timeout:90000});
    await p.evaluate(()=>document.fonts.ready); await p.waitForTimeout(900); await p.screenshot({path:__dirname+'/'+f.replace('.svg','.png')}); await p.close(); }
  await b.close(); })();
