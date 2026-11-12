#!/usr/bin/env python3
"""
地方競馬(NAR)公式データ ダウンロード＆変換パイプライン
出典: https://www.keiba.go.jp/ データダウンロード機能（公式・無料）
マニュアル: https://www.keiba.go.jp/pdf/manual/data_pdf_manual.pdf

これで netkeiba スクレイピング（proxy WAF障害・EUC-JP文字化け・パース失敗）を
公式CSV（UTF-8・構造化・全13場・1998年〜）に置き換えられる。

使い方:
  python3 nar_data_pipeline.py 202601 202607   # 2026年1月〜7月を取得・変換
  → pays_official.json（払戻）, odds_official.json（オッズ）, hist_official.json（馬別履歴）を生成

データ提供範囲:
  レース情報: 1998年1月〜  /  オッズ情報: 2026年3月〜
  当日ファイルは約2分ごと更新、月次は毎日夜間更新
"""
import csv, glob, json, os, sys, subprocess

TRACK_CODE = {'門別':'30','盛岡':'35','水沢':'36','浦和':'42','船橋':'43','大井':'44',
              '川崎':'45','金沢':'46','笠松':'47','名古屋':'48','園田':'50','姫路':'51',
              '高知':'54','佐賀':'55','帯広ば':'65'}

BASE = "https://www.keiba.go.jp/KeibaWeb/DataDownload"
# ★絶対パスにする★ 相対パス "nardata" だと、実行時のカレントディレクトリ次第で
#   リポジトリ直下に誤って書き出す事故があった（2026-07-21・7/18-20の払戻更新が
#   backtest/nardata/ に届かず、古いデータのまま「ラグがある」と誤診断した）。
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nardata")

def months(start, end):
    """YYYYMM の範囲を列挙"""
    y,m = int(start[:4]), int(start[4:6])
    ey,em = int(end[:4]), int(end[4:6])
    out=[]
    while (y,m) <= (ey,em):
        out.append(f"{y}{m:02d}"); m+=1
        if m>12: m=1; y+=1
    return out

def download(ym_list, kind):
    """kind: 'race' or 'odds'。月次ZIPを取得して解凍"""
    os.makedirs(f"{WORK}/all", exist_ok=True)
    ep = "RaceDataDownload" if kind=="race" else "OddsDataDownload"
    for ym in ym_list:
        y, m = ym[:4], str(int(ym[4:6]))
        url = f"{BASE}/{ep}?type=monthly&k_year={y}&k_month={m}"
        zf = f"{WORK}/{kind}_{ym}.zip"
        subprocess.run(["curl","-sL","--max-time","120",url,"-o",zf], check=False)
        sz = os.path.getsize(zf) if os.path.exists(zf) else 0
        print(f"  {kind} {ym}: {sz//1024}KB")
        if sz>1000:
            subprocess.run(["unzip","-o","-d",f"{WORK}/all",zf],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def load(fn): return list(csv.reader(open(fn, encoding='utf-8-sig')))

def rid_of(track, date, rno):
    tc = TRACK_CODE.get(track)
    return date+tc+rno.zfill(2) if tc else None

def build_pays():
    """払戻: {rid:{tan:{num:yen}, fuku:{num:yen}, wide:{a-b:yen}}}"""
    pays={}
    for fn in sorted(glob.glob(f"{WORK}/all/*_payback.csv")):
        for r in load(fn)[1:]:
            if len(r)<16: continue
            rid = rid_of(r[0],r[1],r[2])
            if not rid: continue
            d={'tan':{},'fuku':{},'wide':{}}
            if r[4] and r[5] and r[5].isdigit(): d['tan'][r[4]]=int(r[5])
            for oi,pi in [(7,8),(10,11),(13,14)]:
                if len(r)>pi and r[oi] and r[pi] and r[pi].isdigit(): d['fuku'][r[oi]]=int(r[pi])
            for a,b,p in [(32,33,34),(36,37,38),(40,41,42)]:
                if len(r)>p and r[a] and r[b] and r[p] and r[p].isdigit(): d['wide'][r[a]+'-'+r[b]]=int(r[p])
            pays[rid]=d
    json.dump(pays, open("pays_official.json","w"))
    print(f"pays_official.json: {len(pays)} レース")

def build_odds():
    """単勝オッズ: {rid:{num:{odds,pop}}}"""
    odds={}
    for fn in sorted(glob.glob(f"{WORK}/all/*odds.csv")):
        for r in load(fn):
            if len(r)<10 or r[3]!='単勝': continue
            rid = rid_of(r[0],r[1],r[2])
            if not rid: continue
            try: od=float(r[7]); pop=int(r[9]) if r[9] else None
            except: continue
            odds.setdefault(rid,{})[r[4]]={'odds':od,'pop':pop}
    json.dump(odds, open("odds_official.json","w"))
    print(f"odds_official.json: {len(odds)} レース")

def build_hist():
    """馬別履歴（近走再構築用）: {馬名:[{date,track,rno,num,rank,time,last3f,pop}...] 日付順}"""
    from collections import defaultdict
    hist=defaultdict(list)
    for fn in sorted(glob.glob(f"{WORK}/all/*_horselist.csv")):
        for r in load(fn):
            if len(r)<36 or r[0]=='競馬場': continue
            hist[r[6]].append({'date':r[1],'track':r[0],'rno':r[2],'num':r[5],
                               'rank':r[31],'time':r[32],'last3f':r[34],'pop':r[35]})
    for name in hist: hist[name].sort(key=lambda x:x['date'])
    json.dump(hist, open("hist_official.json","w"), ensure_ascii=False)
    print(f"hist_official.json: {len(hist)} 頭")

if __name__=="__main__":
    if len(sys.argv)<3:
        print("使い方: python3 nar_data_pipeline.py <開始YYYYMM> <終了YYYYMM>")
        print("例:     python3 nar_data_pipeline.py 202601 202607")
        sys.exit(1)
    yms = months(sys.argv[1], sys.argv[2])
    print(f"対象: {sys.argv[1]}〜{sys.argv[2]}（{len(yms)}ヶ月）")
    print("--- レース情報DL ---"); download(yms,"race")
    print("--- オッズ情報DL（2026年3月〜のみ有効）---"); download(yms,"odds")
    print("--- 変換 ---")
    build_pays(); build_odds(); build_hist()
    print("完了。pays_official.json / odds_official.json / hist_official.json を生成しました。")
