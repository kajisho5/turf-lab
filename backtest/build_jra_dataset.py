# -*- coding: utf-8 -*-
"""中央競馬(JRA)を地方と同じ形式のデータセットにする

★なぜ必要か★
  人格(core/personas.js)は ar/fpf/wr/dr/age/wk/pop を要求するが、
  jra_all.jsonl には {馬番,着順,オッズ,人気} しか無い。
  これでは中央で人格を測ることも表示することもできない。

  地方は build_dataset.py が bt_all.jsonl を作っている。**同じ形**にすることで、
  bt_personas.js を1行も変えずに中央でも回せる。形が違うと必ず分岐が増え、
  分岐が増えると地方と中央で違う計算をしていることに気づけなくなる。

★列位置は仕様書ではなく実データで同定した★
  最初 cp932 に decode してから文字位置で探し、全部ずれた。
  既存パーサーは**バイト位置**で読んでいる（馬名の漢字以降がずれる）。
  同定に使った制約:
    枠(27)      1〜8 で、馬番順に単調非減少          100%
    馬番(28)    レース内で 1..N の順列                100%
    馬齢(82)    2〜12 の範囲                          100%
    着順(334)   レース内で 1..N（取消があるので84%）
    コーナー(351/353/355/357)
                着順との相関が +0.19 → +0.21 → +0.35 → +0.47 と
                後ろの角ほど強くなる（物理的に正しい並び）
    距離(697)   1200/1600/1800/2000 など実在の距離が上位
    トラック(705) 24=ダ 17=芝 23=ダ 11=芝 54=障 と実在コード

出力: backtest/nardata/bt_jra.jsonl（1行=1レース・bt_all.jsonl と同じ形）
使い方: python backtest/build_jra_dataset.py
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = [os.path.join(ROOT, "backtest", "jvdata", "target_all.txt"),
        os.path.join(ROOT, "backtest", "jvdata", "setup_2026.txt")]
OUT = os.path.join(ROOT, "backtest", "nardata", "bt_jra.jsonl")

N_PAST = 3          # 地方と揃える。ここを変えると ar/fpf/np の意味が変わる

# --- SE（馬毎レース情報）のバイト位置 ---
S_KEY, S_WK, S_UMA, S_KETTO = slice(11, 27), slice(27, 28), slice(28, 30), slice(30, 40)
S_NAME, S_AGE, S_WT, S_WD = slice(40, 76), slice(82, 84), slice(324, 327), slice(327, 331)
S_FIN, S_ODDS, S_POP = slice(334, 336), slice(359, 363), slice(363, 365)
S_C1, S_C4 = slice(351, 353), slice(357, 359)
S_JK = slice(306, 314)     # 騎手名（bt_jra_combo等と同じ位置）
S_TR = slice(90, 98)       # 調教師略称（docs/DATA_SOURCES.md の検証済み位置）


def _days(a, b):
    import datetime
    try:
        return (datetime.date(int(a[:4]), int(a[4:6]), int(a[6:8]))
                - datetime.date(int(b[:4]), int(b[4:6]), int(b[6:8]))).days
    except Exception:
        return None
# --- RA（レース詳細） ---
R_KEY, R_DIST, R_TRACK = slice(11, 27), slice(697, 701), slice(705, 707)
# ★2026-07-30追加: 馬場状態★ 芝=888 / ダート=889（1バイト・0なし 1良 2稍 3重 4不良）。
#   位置は setup_2026.txt の実データで特定した（芝レースでは888が非0でダ889が0、
#   ダートレースでは逆という相補パターン。分布も良7割/稍2割の実勢と一致）。
#   ★これは当日情報なので事前予想モデルには使わない★（DAY_ONLYでgoingは除外済み）。
#   目的は天気→馬場の較正表を中央でも作れるようにすること（表示用）と、
#   「馬場が分かっても精度が上がらない」ceilingテストを中央でも回せるようにすること。
R_SIBA_BABA, R_DIRT_BABA = slice(888, 889), slice(889, 890)
GOING_NAME = {1: "良", 2: "稍重", 3: "重", 4: "不良"}
# --- HR（払戻）。位置は parse_jvdata.py で検証済みのものを使う ---
H_KEY = slice(11, 27)
H_TAN = (102, 3, 2, 13)
H_FUKU = (141, 5, 2, 13)
# ★2026-07-30追加: エキゾチック券種★
#   位置は backtest/parse_jvdata.py の HR_BLOCKS（--verifyで
#   「馬連の組=着順上位2頭」「3連単の組=上位3頭の順序通り」を実データ照合済み）から転記。
#   ★ワイドは10枠★（7と誤ると以降が全部ずれる）
#   ★3連単だけ1件19バイト★（18で読むと2件目以降がずれ1億円級が混入する）
H_WIDE = (293, 10, 4, 16)
H_UMAREN = (245, 3, 4, 16)
H_UMATAN = (453, 6, 4, 16)
H_SANPUKU = (549, 3, 6, 18)
H_SANTAN = (603, 6, 6, 19)
# 組の桁数 → 馬番リストへの分解（2桁ずつ。"0207" → ["2","7"]）
def _combo(k):
    try:
        return [str(int(k[i:i + 2])) for i in range(0, len(k), 2)]
    except ValueError:
        return None

JYO = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}


def num(b):
    s = b.decode("ascii", "replace").strip()
    return int(s) if s.lstrip("+-").isdigit() else None


def blocks(rec, start, cnt, kd, ln):
    """(組, 払戻) を取り出す。払戻9桁・人気は残り。単勝/複勝用（馬番1つ）"""
    out = {}
    for i in range(cnt):
        p = start + i * ln
        k = rec[p:p + kd].decode("ascii", "replace").strip()
        y = rec[p + kd:p + kd + 9].decode("ascii", "replace").strip()
        if k and y.isdigit() and int(y) > 0:
            out[str(int(k))] = int(y)
    return out


def combo_blocks(rec, start, cnt, kd, ln):
    """組み合わせ券種 → {"2-7": 250} 形式。地方(bt_all)の wide と同じ形に揃える。
    ★順序は組のバイト列のまま★ 馬単・3連単は着順どおりなので並べ替えない
    （eval_bets.py が ordered=True で照合する）。"""
    out = {}
    for i in range(cnt):
        p = start + i * ln
        k = rec[p:p + kd].decode("ascii", "replace").strip()
        y = rec[p + kd:p + kd + 9].decode("ascii", "replace").strip()
        if not (k and y.isdigit() and int(y) > 0):
            continue
        c = _combo(k)
        if c:
            out["-".join(c)] = int(y)
    return out


def main():
    ra, hr = {}, {}
    se = collections.defaultdict(list)
    for path in DUMP:
        if not os.path.exists(path):
            print(f"  無い: {path}")
            continue
        with open(path, "rb") as f:
            for line in f:
                t = line[:2]
                if t == b"SE":
                    se[line[S_KEY]].append(line)
                elif t == b"RA":
                    ra[line[R_KEY]] = line
                elif t == b"HR":
                    hr[line[H_KEY]] = line
        print(f"  読了 {os.path.basename(path)}  RA{len(ra):,} SE{len(se):,} HR{len(hr):,}", flush=True)

    # ★日付順に処理する★ 過去走から特徴量を作るので、順序を間違えると
    #   「未来の結果」で予想したことになり、成績が実際より良く出る。
    keys = sorted(se, key=lambda k: (k[:8].decode(), k[14:16].decode()))

    hist = collections.defaultdict(list)       # 血統番号 -> [(位置率, 着順)]
    trk = collections.defaultdict(lambda: [0, 0])   # (馬,場) -> [出走,複勝]
    dst = collections.defaultdict(lambda: [0, 0])   # (馬,距離帯) -> [出走,複勝]
    # 馬 -> [通算出走, 勝, 連対, 複勝, 最後に勝ってからの走数]（★2026-07-30 NARと同構成に拡張）
    car = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
    sea = collections.defaultdict(lambda: [[0, 0], [0, 0], [0, 0], [0, 0]])  # 季節適性
    jkr = collections.defaultdict(lambda: [0, 0])   # 騎手 -> [騎乗数, 複勝数]（リークなし）
    trr = collections.defaultdict(lambda: [0, 0])   # 調教師 -> [出走数, 複勝数]（同上）

    n_out = skip = 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # ★一時ファイルに書いてから差し替える★（地方側 build_dataset.py と同じ保護）
    #   2026-07-30に日次(daily.py)へ載せたので必須になった。
    #   OUT を直接開くと、JV-Dataのダンプが無い日に**空のファイルで上書きして
    #   bt_jra.jsonl(140,337R)を消す**。中央成績・払戻・馬場が道連れになる。
    tmp_out = OUT + ".tmp"
    with open(tmp_out, "w", encoding="utf-8") as fo:
        for k in keys:
            rows = se[k]
            r_ra = ra.get(k)
            if not r_ra:
                skip += 1
                continue
            dist = num(r_ra[R_DIST])
            track = r_ra[R_TRACK].decode("ascii", "replace")
            surf = "芝" if track[:1] == "1" else ("ダート" if track[:1] == "2" else "障害")
            # 馬場状態: 芝レースは芝馬場、それ以外はダート馬場を見る
            _bb = num(r_ra[R_SIBA_BABA] if surf == "芝" else r_ra[R_DIRT_BABA])
            going = GOING_NAME.get(_bb)
            band = str(dist // 200 * 200) if dist else None

            date = k[:8].decode()
            jyo = k[8:10].decode()
            rno = int(k[14:16])
            fin = [(r, num(r[S_FIN])) for r in rows]
            live = [(r, f) for r, f in fin if f]
            fn = len(live)
            if fn < 5:
                skip += 1
                continue

            horses = []
            for r, f in live:
                key = r[S_KETTO].decode("ascii", "replace")
                past = hist[key][-N_PAST:]
                pfs = [p[0] for p in past if p[0] is not None]
                rks = [p[1] for p in past]
                t = trk[(key, jyo)]
                d = dst[(key, band)]
                c = car[key]                        # レース前の通算成績（先読みなし）
                horses.append({
                    "n": str(num(r[S_UMA])), "rk": f, "pop": num(r[S_POP]),
                    "wk": num(r[S_WK]), "age": num(r[S_AGE]),
                    "ar": round(sum(rks) / len(rks), 3) if rks else None,
                    "fpf": round(sum(pfs) / len(pfs), 4) if pfs else None,
                    "lpf": pfs[-1] if pfs else None,
                    "bpf": min(pfs) if pfs else None,
                    "np": len(past),
                    # ★3走未満の率は暴れるので使わない（地方と同じ基準）
                    "wr": round(t[1] / t[0], 4) if t[0] >= 3 else None,
                    "dr": round(d[1] / d[0], 4) if d[0] >= 3 else None,
                    # ★通算勝率/連対率（無条件・密。1走以上で埋まる＝当地/当距離の穴を埋める主軸）
                    "owr": round(c[1] / c[0], 4) if c[0] >= 1 else None,
                    "o2r": round(c[2] / c[0], 4) if c[0] >= 1 else None,
                    "wt": num(r[S_WT]), "wd": num(r[S_WD]),
                    # ---- ★2026-07-30: NARと同じ履歴系（pgap/clvchgはJV-Dataから
                    #      同じ定義で取れないため欠損のまま） ----
                    # past は (pf, rank, date, dist, jyo, pop, wt, jk) の古い順
                    "rest": _days(date, past[-1][2]) if past and len(past[-1]) > 2 else None,
                    "dchg": (dist - past[-1][3]) if past and len(past[-1]) > 3
                            and past[-1][3] and dist else None,
                    "tchg": (1 if past[-1][4] != jyo else 0)
                            if past and len(past[-1]) > 4 else None,
                    "prk": rks[-1] if rks else None,
                    "ppop": past[-1][5] if past and len(past[-1]) > 5 else None,
                    "pmiss": (rks[-1] - past[-1][5])
                             if rks and past and len(past[-1]) > 5
                             and past[-1][5] is not None else None,
                    "trend": (round(sum(rks[:-1]) / len(rks[:-1]) - rks[-1], 3)
                              if len(rks) >= 2 else None),
                    "vrank": (max(rks) - min(rks)) if len(rks) >= 2 else None,
                    "cn": c[0] or None,
                    "ct3": round(c[3] / c[0], 4) if c[0] >= 3 else None,
                    "wma": (lambda _w, _ws: (_w - round(sum(_ws) / len(_ws)))
                            if _w and _ws else None)(
                            num(r[S_WT]),
                            [pp[6] for pp in past if len(pp) > 6 and pp[6]]),
                    "swin": c[4] if c[0] >= 1 else None,
                    "jkchg": (lambda _pj, _cj: (0 if _pj == _cj else 1)
                              if _pj and _cj else None)(
                              past[-1][7] if past and len(past[-1]) > 7 else None,
                              r[S_JK].decode("cp932", "replace").strip()),
                    "restdev": (lambda _g, _r: (_r - sum(_g) / len(_g))
                                if _g and len(_g) >= 2 and _r is not None else None)(
                                [d for d in (_days(past[i + 1][2], past[i][2])
                                             for i in range(len(past) - 1)
                                             if len(past[i]) > 2 and len(past[i + 1]) > 2)
                                 if d is not None],
                                _days(date, past[-1][2]) if past and len(past[-1]) > 2 else None),
                    "sqr": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 3 else None)(
                            sea[key][(int(date[4:6]) - 1) // 3]),
                    # ★2026-07-30 第3弾★ 騎手の事前複勝率（地方で+1.27pt[CI +0.97,+1.55]と
                    # 大きく効いた列。50騎乗未満は率が暴れるので欠損）
                    "jkr": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 50 else None)(
                            jkr[r[S_JK].decode("cp932", "replace").strip()]),
                    "trr": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 50 else None)(
                            trr[r[S_TR].decode("cp932", "replace").strip()]),
                })

            pay = {}
            h = hr.get(k)
            if h:
                pay["tan"] = blocks(h, *H_TAN)
                pay["fuku"] = blocks(h, *H_FUKU)
                # ★2026-07-30★ ROIを全券種で測れるようにエキゾチックも入れる
                # （ユーザー指摘「単複と◎○から流した的中率・回収率で判定して」）
                pay["wide"] = combo_blocks(h, *H_WIDE)
                pay["umaren"] = combo_blocks(h, *H_UMAREN)
                pay["umatan"] = combo_blocks(h, *H_UMATAN)
                pay["sanpuku"] = combo_blocks(h, *H_SANPUKU)
                pay["santan"] = combo_blocks(h, *H_SANTAN)

            fo.write(json.dumps({
                "rid": date + jyo + f"{rno:02d}", "d": date, "tc": jyo,
                "jyo": JYO.get(jyo, jyo), "r": rno, "fn": fn,
                "surf": surf, "dist": dist, "going": going, "h": horses, "pay": pay,
            }, ensure_ascii=False) + "\n")
            n_out += 1

            # --- 走り終えてから履歴に足す（先読み防止） ---
            _q = (int(date[4:6]) - 1) // 3
            for r, f in live:
                key = r[S_KETTO].decode("ascii", "replace")
                c4 = num(r[S_C4])
                hist[key].append((c4 / fn if c4 else None, f, date, dist, jyo,
                                  num(r[S_POP]), num(r[S_WT]),
                                  r[S_JK].decode("cp932", "replace").strip()))
                if len(hist[key]) > 10:
                    hist[key] = hist[key][-10:]
                t = trk[(key, jyo)]
                t[0] += 1
                t[1] += (f <= 3)
                d = dst[(key, band)]
                d[0] += 1
                d[1] += (f <= 3)
                c = car[key]                        # 通算（無条件）
                c[0] += 1
                c[1] += (f == 1)
                c[2] += (f <= 2)
                c[3] += (f <= 3)
                c[4] = 0 if f == 1 else c[4] + 1
                e = sea[key][_q]
                e[0] += 1
                e[1] += (f <= 3)
                _jk = r[S_JK].decode("cp932", "replace").strip()
                if _jk:                                # 騎手の通算（特徴量計算の後＝リークなし）
                    j = jkr[_jk]
                    j[0] += 1
                    j[1] += (f <= 3)
                _tr = r[S_TR].decode("cp932", "replace").strip()
                if _tr:                                # 調教師の通算（同上）
                    t_ = trr[_tr]
                    t_[0] += 1
                    t_[1] += (f <= 3)

            if n_out % 20000 == 0:
                print(f"  {n_out:,}レース", flush=True)

    # 1レースも書けていないなら差し替えない（入力が無い/壊れている日に本体を消さない）
    if n_out == 0:
        os.remove(tmp_out)
        print("0レース。入力(jvdata)が無いか壊れている → 既存の bt_jra.jsonl は温存した")
        return 1
    os.replace(tmp_out, OUT)

    # ★騎手・調教師の集計をサイドカーに書き出す★（build_jockey_index.py が索引に変換）
    try:
        for suffix, table in ((".jockeys", jkr), (".trainers", trr)):
            with open(OUT + suffix, "w", encoding="utf-8") as jf:
                for nm, (n, t3) in sorted(table.items()):
                    if n:
                        jf.write(json.dumps([nm, n, t3], ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"  騎手/調教師サイドカーの書き出し失敗（本体は無事）: {e}")

    print(f"\n出力: {os.path.relpath(OUT, ROOT)}  {n_out:,}レース（除外 {skip:,}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
