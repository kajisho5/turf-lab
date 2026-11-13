# -*- coding: utf-8 -*-
"""投稿画像の新デザイン案（見本）。python3 gen.py → a.svg b.svg c.svg d.svg。名前と数字は全部架空"""
import html
RACES = [
 dict(no=1, cls="C3ー5", post="15:35", tier="battle", strong="近走の時計がメンバー1位",
      m=[("◎",5,"オッターダッシュ",64),("○",7,"ラッコノユメ",31),("▲",2,"カワウソブレイブ",None),("△",4,"セセラギキング",None),("△",6,"ミズカキエース",None)]),
 dict(no=2, cls="2歳ー3", post="16:05", tier="aim", strong=None,
      m=[("◎",10,"イタチノホシ",52),("○",3,"コツメスマイル",45),("▲",6,"ナガレボシオー",None),("△",1,"カワベノハナ",None),("△",2,"ツキヨノラッコ",None)]),
 dict(no=3, cls="C2ー4", post="16:40", tier="", strong=None,
      m=[("◎",2,"ミナモノカゼ",47),("○",9,"シオカゼテイオー",41),("▲",4,"ハマベノユウヒ",None),("△",3,"ナギサブルー",None),("△",8,"ウミネコライト",None)]),
 dict(no=4, cls="B3ー2", post="17:15", tier="", strong=None,
      m=[("◎",8,"セセラギオウジ",49),("○",1,"カワモノガタリ",44),("▲",5,"ヨアケノラッコ",None),("△",11,"ミズベノユメ",None),("△",6,"アサナギスター",None)]),
]
RES = [
 dict(no=1, cls="C3ー5", tier="battle", hit="的中　単勝 180円／複勝 110円", ok=True,
      m=[("◎",5,"オッターダッシュ","1着"),("○",7,"ラッコノユメ","3着"),("▲",2,"カワウソブレイブ","6着"),("△",4,"セセラギキング","2着"),("△",6,"ミズカキエース","9着")]),
 dict(no=2, cls="2歳ー3", tier="aim", hit="外れ（◎は5着）", ok=False,
      m=[("◎",10,"イタチノホシ","5着"),("○",3,"コツメスマイル","1着"),("▲",6,"ナガレボシオー","2着"),("△",1,"カワベノハナ","7着"),("△",2,"ツキヨノラッコ","4着")]),
]
e = html.escape
def T(x,y,s,size,fill,w=400,anchor="start",fam=None,ls=None):
    a=f' font-family="{fam}"' if fam else ""; l=f' letter-spacing="{ls}"' if ls else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}"{a}{l}>{e(str(s))}</text>'
def R(x,y,w,h,fill,r=0,stroke=None,sw=0,extra=""):
    st=f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{st}{extra}/>'

def build(t):
    W,H=1240,1710; o=[]
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{t["jp"]}">')
    o.append(t.get("defs","")); o.append(R(0,0,W,H,t["bg"]))
    o.append(t["header"](t))
    # 朝のカード 2×2
    cw,ch,x0,y0,gx,gy=554,392,48,t["top"],36,28
    for i,rc in enumerate(RACES):
        x=x0+(i%2)*(cw+gx); y=y0+(i//2)*(ch+gy); o.append(card(t,x,y,cw,ch,rc,False))
    y=y0+2*(ch+gy)+16
    o.append(t["section"](t,y,"答え合わせ（夜）")); y+=64
    for i,rc in enumerate(RES):
        x=x0+i*(cw+gx); o.append(card(t,x,y,cw,ch,rc,True))
    y+=ch+34
    o.append(R(48,y,W-96,2,t.get("foot_rule",t["rule"]))); o.append(T(48,y+40,"外れも全部のせます。回収率は買った全レースが分母　／　馬券は20歳から",22,t.get("foot_ink",t["sub"])))
    o.append(t.get("foot",lambda t,W,H:"")(t,W,H)); o.append("</svg>"); return "\n".join(o)

def card(t,x,y,w,h,rc,res):
    tier=rc["tier"]; c=t["tiers"].get(tier,t["tiers"][""]); o=[]
    o.append(t["cardbox"](t,x,y,w,h,tier))
    # 見出し行
    o.append(t["rno"](t,x+20,y+18,rc["no"],tier))
    o.append(T(x+110,y+56,rc["cls"],30,t["ink"],700))
    if not res: o.append(T(x+110+len(rc["cls"])*30+16,y+56,rc["post"],26,t["sub"],400,fam=t["num"]))
    lab={"battle":"★勝負","aim":"狙い目"}.get(tier)
    if lab: o.append(t["tag"](t,x+w-20,y+22,lab,tier))
    o.append(R(x+20,y+78,w-40,2,t["rule"]))
    ry=y+92; rh=44
    for k,(mk,num,name,v) in enumerate(rc["m"]):
        big=(mk=="◎"); yy=ry+k*rh+(8 if k>0 else 0)
        hh=rh+8 if big else rh
        if big: o.append(t["toprow"](t,x+14,yy-2,w-28,hh,tier))
        base=yy+(36 if big else 31)
        o.append(T(x+28,base,mk,34 if big else 28,t["marks"][mk],700))
        o.append(T(x+106,base,num,34 if big else 28,t["marks"][mk] if t.get("numcolor") else t["ink"],700,anchor="end",fam=t["num"]))
        o.append(T(x+126,base,name,30 if big else 27,t["ink"],700 if big else 500))
        if res:
            col=t["win"] if v=="1着" else (t["place"] if v in("2着","3着") else t["sub"])
            o.append(T(x+w-28,base,v,28 if big else 26,col,700,anchor="end"))
        elif v is not None:
            o.append(t["score"](t,x+w-28,base,v,big))
    by=y+h-26
    if res:
        o.append(T(x+24,by,rc["hit"],24,t["win"] if rc["ok"] else t["sub"],700))
    elif rc.get("strong"):
        o.append(t["strong"](t,x+24,by,rc["strong"]))
    return "\n".join(o)

# ---------- A: 競馬新聞 ----------
A=dict(name="a", jp="'Noto Sans JP',sans-serif", num="'Roboto Condensed','Noto Sans JP',sans-serif", bg="#f3eee2", ink="#161616", sub="#4d4a44", rule="#161616", top=250,
  win="#b3001b", place="#161616", marks={"◎":"#b3001b","○":"#161616","▲":"#161616","△":"#4d4a44"},
  tiers={"":{}, "battle":{}, "aim":{}})
def a_header(t):
    s=[R(48,44,1144,6,"#161616"),R(48,54,1144,2,"#161616")]
    s.append(T(48,150,"潮見",96,"#161616",900,fam="'Noto Serif JP',serif")); s.append(T(260,112,"カジ競馬",26,"#161616",700)); s.append(T(260,150,"AI予想　11月14日（土）",30,"#161616",700))
    s.append(R(880,84,312,72,"#b3001b")); s.append(T(1036,132,"★勝負 3　狙い目 6",30,"#ffffff",700,"middle"))
    s.append(R(48,176,1144,2,"#161616")); s.append(T(48,216,"◎本命　○対抗　▲単穴　△押さえ　／　数字は◎○の点数（オッズを見る前の評価）",22,"#4d4a44"))
    return "\n".join(s)
A["header"]=a_header
A["section"]=lambda t,y,s: R(48,y,1144,6,"#161616")+T(48,y+52,s,36,"#161616",900,fam="'Noto Serif JP',serif")
A["cardbox"]=lambda t,x,y,w,h,tier: R(x,y,w,h,"#fbf8f0",0,"#161616",4 if tier=="battle" else 2)+(R(x,y,w,10,"#b3001b") if tier=="battle" else "")
A["rno"]=lambda t,x,y,no,tier: R(x,y+2,74,52,"#b3001b" if tier=="battle" else "#161616")+T(x+37,y+40,f"{no}R",30,"#ffffff",700,"middle",fam=t["num"])
A["tag"]=lambda t,xr,y,lab,tier: (R(xr-132,y,132,44,"#b3001b")+T(xr-66,y+32,lab,26,"#ffffff",700,"middle")) if tier=="battle" else (R(xr-116,y,116,44,"#fbf8f0",0,"#b3001b",3)+T(xr-58,y+32,lab,26,"#b3001b",700,"middle"))
A["toprow"]=lambda t,x,y,w,h,tier: R(x,y,w,h,"#f1e3d3")+R(x,y,6,h,"#b3001b")
A["score"]=lambda t,xr,base,v,big: T(xr,base,v,30 if big else 26,"#161616" if big else "#4d4a44",700,"end",fam=t["num"])
A["strong"]=lambda t,x,y,s: R(x,y-28,76,36,"#161616")+T(x+38,y-2,"強み",22,"#ffffff",700,"middle")+T(x+90,y-2,s,24,"#161616",500)

# ---------- B: 電光掲示板 ----------
B=dict(name="b", jp="'Noto Sans JP',sans-serif", num="'Chakra Petch','Noto Sans JP',sans-serif", bg="#060708", ink="#f4f4f4", sub="#aab0b8", rule="#2a2f36", top=250, numcolor=True,
  win="#19e68c", place="#ffb300", marks={"◎":"#ffb300","○":"#f4f4f4","▲":"#57b8ff","△":"#aab0b8"}, tiers={"":{}, "battle":{}, "aim":{}})
def b_header(t):
    s=[R(0,0,1240,12,"#ffb300")]
    s.append(T(48,150,"潮見",104,"#f4f4f4",900)); s.append(T(276,104,"KAJI KEIBA  AI",26,"#ffb300",700,fam=t["num"],ls="4")); s.append(T(276,150,"2026.11.14 SAT",40,"#f4f4f4",700,fam=t["num"]))
    s.append(R(808,84,184,72,"#ffb300",8)); s.append(T(900,132,"★勝負 3",30,"#060708",700,"middle"))
    s.append(R(1008,84,184,72,"#060708",8,"#19e68c",3)); s.append(T(1100,132,"狙い目 6",30,"#19e68c",700,"middle"))
    s.append(R(48,180,1144,2,"#2a2f36")); s.append(T(48,220,"◎本命　○対抗　▲単穴　△押さえ　／　数字は◎○の点数（オッズを見る前の評価）",22,"#aab0b8"))
    return "\n".join(s)
B["header"]=b_header
B["section"]=lambda t,y,s: R(48,y+12,12,40,"#19e68c")+T(76,y+48,s,36,"#f4f4f4",900)
B["cardbox"]=lambda t,x,y,w,h,tier: R(x,y,w,h,"#0f1215",6,{"battle":"#ffb300","aim":"#19e68c"}.get(tier,"#2a2f36"),3 if tier else 2)
B["rno"]=lambda t,x,y,no,tier: T(x+4,y+44,f"{no:02d}",48,{"battle":"#ffb300","aim":"#19e68c"}.get(tier,"#aab0b8"),700,fam=t["num"])+T(x+66,y+44,"R",24,"#aab0b8",700,fam=t["num"])
B["tag"]=lambda t,xr,y,lab,tier: (R(xr-132,y,132,44,"#ffb300",4)+T(xr-66,y+32,lab,26,"#060708",700,"middle")) if tier=="battle" else (R(xr-116,y,116,44,"#0f1215",4,"#19e68c",2)+T(xr-58,y+32,lab,26,"#19e68c",700,"middle"))
B["toprow"]=lambda t,x,y,w,h,tier: R(x,y,w,h,"#1c1a10" if tier!="aim" else "#0f1f18",4)
def b_score(t,xr,base,v,big):
    col="#ffb300" if big else "#aab0b8"; bw=70; x=xr-bw
    return T(x-14,base,v,30 if big else 26,col,700,"end",fam=t["num"])+R(x,base-16,bw,12,"#2a2f36",6)+R(x,base-16,bw*v/100,12,col,6)
B["score"]=b_score
B["strong"]=lambda t,x,y,s: R(x,y-28,76,36,"#060708",4,"#57b8ff",2)+T(x+38,y-2,"強み",22,"#57b8ff",700,"middle")+T(x+90,y-2,s,24,"#f4f4f4",500)

# ---------- C: 芝と白いカード ----------
C=dict(name="c", foot_ink="#e3efe8", foot_rule="#3f7a63", jp="'Noto Sans JP',sans-serif", num="'Roboto Condensed','Noto Sans JP',sans-serif", bg="url(#turf)", ink="#12261d", sub="#4c5f56", rule="#d9e2dc", top=250,
  defs='<defs><linearGradient id="turf" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0f5a3e"/><stop offset="1" stop-color="#083324"/></linearGradient></defs>',
  win="#b3261e", place="#0b6b47", marks={"◎":"#b3261e","○":"#12261d","▲":"#1257a6","△":"#4c5f56"}, tiers={"":{}, "battle":{}, "aim":{}})
def c_header(t):
    s=[T(48,150,"潮見",104,"#ffffff",900)]; s.append(T(276,104,"カジ競馬　AI予想",26,"#ffe08a",700)); s.append(T(276,150,"11月14日（土）",40,"#ffffff",700))
    s.append(R(808,84,184,72,"#ffd43d",36)); s.append(T(900,132,"★勝負 3",30,"#12261d",700,"middle"))
    s.append(R(1008,84,184,72,"#ffffff",36)); s.append(T(1100,132,"狙い目 6",30,"#b3261e",700,"middle"))
    s.append(T(48,220,"◎本命　○対抗　▲単穴　△押さえ　／　数字は◎○の点数（オッズを見る前の評価）",22,"#e3efe8"))
    return "\n".join(s)
C["header"]=c_header
C["section"]=lambda t,y,s: T(48,y+48,s,36,"#ffffff",900)
C["cardbox"]=lambda t,x,y,w,h,tier: R(x,y,w,h,"#ffffff",24,{"battle":"#ffd43d","aim":"#ffffff"}.get(tier,"#ffffff"),6 if tier=="battle" else 0)
C["rno"]=lambda t,x,y,no,tier: R(x,y+2,74,52,"#0f5a3e" if tier!="battle" else "#12261d",26)+T(x+37,y+40,f"{no}R",28,"#ffffff",700,"middle",fam=t["num"])
C["tag"]=lambda t,xr,y,lab,tier: (R(xr-132,y,132,44,"#ffd43d",22)+T(xr-66,y+32,lab,26,"#12261d",700,"middle")) if tier=="battle" else (R(xr-116,y,116,44,"#fdecea",22)+T(xr-58,y+32,lab,26,"#b3261e",700,"middle"))
C["toprow"]=lambda t,x,y,w,h,tier: R(x,y,w,h,"#fff6d6" if tier=="battle" else "#eef5f1",14)
def c_score(t,xr,base,v,big):
    col="#0b6b47" if big else "#4c5f56"; bw=70; x=xr-bw
    return T(x-14,base,v,30 if big else 26,col,700,"end",fam=t["num"])+R(x,base-16,bw,12,"#d9e2dc",6)+R(x,base-16,bw*v/100,12,col,6)
C["score"]=c_score
C["strong"]=lambda t,x,y,s: R(x,y-28,76,36,"#1257a6",18)+T(x+38,y-2,"強み",22,"#ffffff",700,"middle")+T(x+90,y-2,s,24,"#12261d",500)

# ---------- D: 今の見た目を整理 ----------
D=dict(name="d", jp="'Noto Sans JP',sans-serif", num="'Saira Condensed','Noto Sans JP',sans-serif", bg="url(#nv)", ink="#ffffff", sub="#cccccc", rule="#333a47", top=250, numcolor=True,
  defs='<defs><linearGradient id="nv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#121826"/><stop offset="1" stop-color="#0a0e16"/></linearGradient><linearGradient id="gold" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffd43d"/><stop offset="1" stop-color="#ff7171"/></linearGradient></defs>',
  win="#51d695", place="#ffd43d", marks={"◎":"#ff7171","○":"#ffd43d","▲":"#57b8ff","△":"#8fd3ae"}, tiers={"":{}, "battle":{}, "aim":{}})
def d_header(t):
    s=[R(48,70,10,84,"#ffd43d",5),T(78,150,"潮見",104,"#ffffff",900)]; s.append(T(306,104,"カジ競馬　AI予想",26,"#cccccc",700)); s.append(T(306,150,"2026.11.14（土）",40,"#ffffff",700,fam=t["num"]))
    s.append(R(808,84,184,72,"url(#gold)",36)); s.append(T(900,132,"★勝負 3",30,"#1a1200",700,"middle"))
    s.append(R(1008,84,184,72,"#171c27",36,"#ff8d44",3)); s.append(T(1100,132,"狙い目 6",30,"#ff8d44",700,"middle"))
    s.append(R(48,180,1144,2,"url(#gold)")); s.append(T(48,220,"◎本命　○対抗　▲単穴　△押さえ　／　数字は◎○の点数（オッズを見る前の評価）",22,"#cccccc"))
    return "\n".join(s)
D["header"]=d_header
D["section"]=lambda t,y,s: R(48,y+12,10,40,"#57b8ff",5)+T(76,y+48,s,36,"#ffffff",900)
D["cardbox"]=lambda t,x,y,w,h,tier: R(x,y,w,h,"#1b1f2b",18,{"battle":"url(#gold)","aim":"#ff8d44"}.get(tier,"#555b66"),4 if tier=="battle" else 2)
D["rno"]=lambda t,x,y,no,tier: R(x,y+2,74,52,"url(#gold)" if tier=="battle" else "#333a47",12)+T(x+37,y+40,f"{no}R",30,"#1a1200" if tier=="battle" else "#ffffff",700,"middle",fam=t["num"])
D["tag"]=lambda t,xr,y,lab,tier: (R(xr-132,y,132,44,"url(#gold)",22)+T(xr-66,y+32,lab,26,"#1a1200",700,"middle")) if tier=="battle" else (R(xr-116,y,116,44,"#1b1f2b",22,"#ff8d44",2)+T(xr-58,y+32,lab,26,"#ff8d44",700,"middle"))
D["toprow"]=lambda t,x,y,w,h,tier: R(x,y,w,h,"#2a2028",10)
def d_score(t,xr,base,v,big):
    col="#ffd43d" if big else "#cccccc"; bw=70; x=xr-bw
    return T(x-14,base,v,30 if big else 26,col,700,"end",fam=t["num"])+R(x,base-16,bw,12,"#333a47",6)+R(x,base-16,bw*v/100,12,col,6)
D["score"]=d_score
D["strong"]=lambda t,x,y,s: R(x,y-28,76,36,"#12303f",8)+T(x+38,y-2,"強み",22,"#57b8ff",700,"middle")+T(x+90,y-2,s,24,"#ffffff",500)
D["foot"]=lambda t,W,H: R(0,H-8,W,8,"url(#gold)")

for t in (A,B,C,D):
    open(t["name"]+".svg","w",encoding="utf-8").write(build(t))
print("ok")
