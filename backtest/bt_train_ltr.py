# -*- coding: utf-8 -*-
"""Learning to Rank（LambdaMART / LightGBM ranker）を地方競馬で学習する

★狙い★
  勝率予測ではなく「レース全頭の順位」を直接学習する（LTR）。GBMと同じ木モデルなので
  JSON にエクスポートして JS で動かせる（＝サイトに載る）。

★正直に評価する★
  train(2023年より前) / holdout(2023年以降) を分ける。
  holdout で「このモデルの◎の複勝率・単複ROI」を出し、**市場（1番人気）と必ず並べる**。
  市場を超えられなければ、それが結論（誇張しない）。

出力:
  backtest/ltr_model.txt   （LightGBM のテキストモデル。JS推論用に別途変換）
  標準出力に holdout 評価
"""
import json
import math
import os
import sys

import numpy as np
import lightgbm as lgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 入力データ・出力モデルは引数で切替（既定=地方）。
#   python bt_train_ltr.py                        → 地方 bt_all.jsonl → ltr_model.txt
#   python bt_train_ltr.py backtest/nardata/bt_jra.jsonl backtest/ltr_model_jra.txt
DATA = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
    os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")
OUT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else \
    os.path.join(ROOT, "backtest", "ltr_model.txt")
SPLIT = os.environ.get("LTR_SPLIT", "20230101")
# ★ハイパラ選抜用★ LTR_MAXDATE で読み込み上限を切る。
#   例: LTR_SPLIT=20220101 LTR_MAXDATE=20230101 → train<2022 / holdout=2022年のみ。
#   最終評価年(2023〜)を見ずにパラメータを選び、勝者だけを通常SPLITで1回評価する。
MAXDATE = os.environ.get("LTR_MAXDATE", "")

# ★市場(pop)は入れない★ 入れると市場の言い換えになる。実力特徴だけで市場に挑む。
# owr/o2r = 通算勝率/通算連対率（無条件・密）。当地/当距離の wr/dr は疎なので主軸をこちらに。
FEATS = ["wk", "age", "ar", "fpf", "lpf", "bpf", "np", "wr", "dr", "owr", "o2r",
         "wt", "wd", "dist", "fn", "going"]

# ★2026-07-29: 履歴系の新特徴量（build_dataset.py で新設）★
#   前走からの間隔・距離変化・前走人気・裏切り度・トレンド・振れ幅・
#   通算・自己体重比・勝ってからの走数・場替わり。
#   これらは旧FEATSから導出できない**新しい情報**。
#   環境変数 LTR_NEWFEATS=0 で旧構成に戻せる（新旧比較用）。
NEW_FEATS = ["rest", "dchg", "tchg", "prk", "ppop", "pmiss",
             "trend", "vrank", "cn", "ct3", "wma", "swin",
             # ★2026-07-30 第2弾★ いずれも事前情報（騎手は前日発表・着差/クラス/季節は履歴）
             "jkchg", "pgap", "restdev", "clvchg", "sqr",
             # ★2026-07-30 第3弾★ 騎手の事前複勝率（初出走馬の唯一の手掛かり）
             "jkr",
             # ★第4弾★ 調教師の事前複勝率（騎手が効いたので同じ理屈で検証）
             "trr",
             # ★第5弾★ 父・母父の事前複勝率（騎手・厩舎と独立した軸）
             "sir", "dms",
             # ★第9弾も却下★ 馬主(own)・生産牧場(brd)の事前複勝率は
             # 16券種中15でROI悪化（3連単マルチ -1.4pt / 単勝○ -1.1pt）。
             # 単勝◎だけ+0.1ptで実質横ばい。充填率も own 48.3% と低い
             # （個人馬主が多く50走に届かない）。列はデータに残す（再検証用）。
             # ★第8弾も却下★ 相手関係(smem/sbeat/slost: 前走で当たった相手が
             # 今日何頭・先着/被先着)は16券種中10でROI悪化
             # (馬単◎→○ -2.4pt / 3連単◎1着流し -1.4pt)。的中率はわずかに上がるが
             # 配当が落ちる＝人気寄りになる典型。前走着順と近走成績で
             # 既に説明されていた。列はデータに残す(再検証用)。
             # ★第7弾も却下★ 騎手・厩舎の直近50走の複勝率（調子）は
             # 16券種中13でROI悪化（3連複◎○軸 -2.0pt / 馬単◎→○ -1.9pt）。
             # 単勝◎は±0で的中率だけ+0.1pt＝人気馬寄りになって配当が下がる典型。
             # 「調子」は通算率＋近走成績で既に説明できていた。列はデータに残す。
             # ★第6弾は却下★ 掛け合わせ（騎手×場/騎手×距離/父×距離）は
             # 16券種中13でROI悪化（馬単◎→○ -2.3pt / 3連単マルチ -3.0pt）。
             # 単体の騎手・厩舎・父が既に持っている情報を細切れにしただけで、
             # 母数が小さくなりノイズが増えた（母父を外した時と同じ現象）。
             # データセットには列を残す（再検証用）が、モデルには入れない。
             ]
# ライブ（race.html）のパーサが現状作れるのは prk/trend/vrank の3列だけ。
# 全列入りのモデルをライブに出すと欠損だらけになり旧より劣化する
# （実測: 全列あり66.56% / prk,trend,vrankのみ65.12% / 旧65.57%）。
# LTR_NEWFEATS=live で「ライブで欠損しない構成」を学習する。
LIVE_SAFE = ["prk", "trend", "vrank"]
# ★当日にしか出ない情報★ 事前予想（前夜）では見えない。
#   馬体重(wt)・増減(wd)・自己平均比(wma)・馬場状態(going)。
#   LTR_NEWFEATS=pre で「事前に分かる情報だけ」の構成を学習する。
DAY_ONLY = ["wt", "wd", "wma", "going"]
# ★LTR_NODMS=1: 母父(dms)を外す★ 公式データの母父名は18.1%が英字表記("A.P.Indy"等)で、
#   netkeiba(カナ)と突き合わせられない＝**本番では18%の馬で欠損する**。
#   バックテストだけ良くて本番で劣化する列を入れない、を機械で担保するためのノブ。
#   父(sir)は英字が1.6%だけなので本番でもほぼ完全に引ける。
_nodms = os.environ.get("LTR_NODMS", "0") == "1"
# ★LTR_MARKET=1: 人気(pop)を特徴量に入れる（LINE配信用・発走直前モデルの実験）★
#   通常モデルは「事前予想＝オッズ前」の制約で市場情報を禁止しているが、
#   発走5分前配信は別プロダクトで、オッズを見られる前提。
#   ★このモデルをtweet.htmlに載せてはいけない★（事前予想の建前が壊れる）
_market = os.environ.get("LTR_MARKET", "0") == "1"
_mode = os.environ.get("LTR_NEWFEATS", "1")
if _mode == "live":
    FEATS = FEATS + LIVE_SAFE
elif _mode == "pre":
    FEATS = [f for f in FEATS + NEW_FEATS if f not in DAY_ONLY]
    # ★LTR_PREGOING=1: 馬場状態(going)だけpre構成に戻す実験★
    #   当日情報なので本番では使えないが、「天気予報から馬場を完璧に予測できた場合の
    #   上限」を測るためのceilingテスト。上限が小さければ予報パイプラインは作らない。
    if os.environ.get("LTR_PREGOING", "0") == "1":
        FEATS = FEATS + ["going"]
elif _mode != "0":
    FEATS = FEATS + NEW_FEATS
if _nodms:
    FEATS = [f for f in FEATS if f != "dms"]
if _market:
    FEATS = FEATS + ["pop"]

# ★2026-07-30 実験ノブ（P3: モデルの技術改善）★
#   LTR_DECAY=<半減期(年)> … 学習サンプルを新しいほど重く（0.5^(経過年/半減期)）。
#     名古屋の1番人気複勝率が10年で-10ptずれた非定常性を追随できるか見る。
#     holdout(2023〜)の評価は変えない。学習の重みだけ。
#   LTR_EPOP=1 … 予想人気(epop)を特徴量に足す。近走平均着順(ar)のレース内昇順順位。
#     ★市場のpopは使わない★ 事前情報だけから作れるレース内相対列。
#   LTR_TC=1 … 場コード(tc)をカテゴリ特徴に足す（場別モデルの安価版）。
#     場を分割すると1場あたりのデータが激減する。分割せず「場の識別子」を
#     カテゴリとして渡し、金沢=先行有利/高知=1番人気弱い等の場固有傾向を
#     木に学習させる。tcは事前に分かる（開催場は確定情報）。
#   LTR_SURF=1 … 芝/ダ/障（中央用。地方は99.6%ダートで無意味）
#   LTR_RNO=1 … レース番号(1-12)。時間帯×クラス編成の構造を持つ事前情報
_decay = float(os.environ.get("LTR_DECAY", "0") or 0)
_epop = os.environ.get("LTR_EPOP", "0") == "1"
_tc = os.environ.get("LTR_TC", "0") == "1"
_surf = os.environ.get("LTR_SURF", "0") == "1"
_rno = os.environ.get("LTR_RNO", "0") == "1"
if _epop:
    FEATS = FEATS + ["epop"]
if _tc:
    FEATS = FEATS + ["tc"]
# ★LTR_TIME=1（2026-11-13）: 時計の7列（build_time_feats.py が bt_all.jsonl に書き足す）★
#   sf1/sfb/sfa=近3走の時計指数、af1/afb/afa=近3走の上がり指数、btf=持ち時計の指数。全部前走までの情報。
TIME_FEATS = ["sf1", "sfb", "sfa", "af1", "afb", "afa", "btf"]
if os.environ.get("LTR_TIME", "0") == "1":
    FEATS = FEATS + TIME_FEATS
if _surf:
    FEATS = FEATS + ["surf"]
if _rno:
    FEATS = FEATS + ["rno"]
if os.environ.get("LTR_RELFEAT", "0") == "1":
    FEATS = FEATS + ["ar_rk", "fpf_rk", "wr_rk", "owr_rk", "jkr_rk", "trr_rk", "sir_rk",
                     "prk_rk", "trend_rk", "ent_style", "n_front", "lone_leader", "front_share"]
# ★LTR_DROP="a,b" … 任意の列を最後に取り除く（新旧比較の対照群を作るため）★
#   例: 中央で「騎手・厩舎の列を入れる前」を再現する → LTR_DROP=jkr,trr,sir
#   中央データセットには sir/dms 列が無い（JV-Linkの血統レコード未取込）ので、
#   中央を学習する時は必ず sir,dms を落とすこと。全欠損列を渡すと木は無視するが、
#   本番モデルの列数が増えて配線チェック（check_model_wiring.js）と食い違う。
_drop = [s.strip() for s in os.environ.get("LTR_DROP", "").split(",") if s.strip()]
if _drop:
    FEATS = [f for f in FEATS if f not in _drop]
CAT_FEATS = ["tc"] if _tc else []
SURF = {"芝": 0, "ダート": 1, "障害": 2}
GOING = {"良": 0, "稍": 1, "稍重": 1, "重": 2, "不": 3, "不良": 3}


def fval(h, rc, k):
    if k == "dist":
        return float(rc.get("dist") or 0) or math.nan
    if k == "tc":
        # NAR='48'等 / JRA='01'〜'10'＋交流の地方コード。海外等('K6')は欠損扱い
        try:
            return float(rc.get("tc")) or math.nan
        except (TypeError, ValueError):
            return math.nan
    if k == "surf":
        return float(SURF.get(rc.get("surf"), math.nan))
    if k == "rno":
        try:
            return float(rc.get("r")) or math.nan
        except (TypeError, ValueError):
            return math.nan
    if k == "fn":
        return float(rc.get("fn") or len(rc.get("h") or [])) or math.nan
    if k == "going":
        g = str(rc.get("going") or "")
        return float(GOING.get(g, GOING.get(g[:1], math.nan)))
    v = h.get(k)
    return float(v) if v is not None else math.nan


# ★LTR_RELFEAT=1: レース内相対＋隊列の特徴を足す（2026-08-02・精度狙い）★
#   狙い: 現行モデルは各馬を**独立**に見ており「このレースの中での相対位置」と
#   「隊列がどうなるか（誰が行くか・同型が何頭か）」を持っていない。
#   LambdaMARTは相対を学ぶが、入力が絶対値のままだと相対情報は木が再発見するしかない。
#   ★データ再構築不要★ レース内の他馬から計算できるものだけ。全て事前情報。
REL_BASE = ["ar", "fpf", "wr", "owr", "jkr", "trr", "sir", "prk", "trend"]
REL_FEATS = [k + "_rk" for k in REL_BASE] + ["ent_style", "n_front", "lone_leader", "front_share"]
_relfeat = os.environ.get("LTR_RELFEAT", "0") == "1"


def add_rel(hs):
    """レース内相対（順位を0-1に正規化）＋隊列構造。欠損は中央値扱い(0.5)。"""
    n = len(hs)
    for k in REL_BASE:
        vals = [(h.get(k), i) for i, h in enumerate(hs)]
        known = [(v, i) for v, i in vals if v is not None]
        # 大きいほど良い特徴は降順、小さいほど良い(ar/prk=着順系, fpf=前ほど小)は昇順
        asc = k in ("ar", "prk", "fpf")
        known.sort(key=lambda t: t[0], reverse=not asc)
        for r, (_v, i) in enumerate(known):
            hs[i][k + "_rk"] = (r / (len(known) - 1)) if len(known) > 1 else 0.5
        for v, i in vals:
            if v is None:
                hs[i][k + "_rk"] = 0.5
    # 隊列: fpf(近走の位置取り 0=前)が小さい＝先行型
    fp = [h.get("fpf") for h in hs if h.get("fpf") is not None]
    n_front = sum(1 for v in fp if v <= 0.35)
    share = (n_front / n) if n else 0.0
    # 脚質エントロピー: 先行/中団/後方の分布の乱雑さ（同型集中か分散か）
    if fp:
        c = [sum(1 for v in fp if v <= 0.35),
             sum(1 for v in fp if 0.35 < v <= 0.6),
             sum(1 for v in fp if v > 0.6)]
        tot = sum(c) or 1
        ent = -sum((x / tot) * math.log((x / tot) + 1e-9) for x in c if x)
    else:
        ent = math.nan
    for h in hs:
        h["ent_style"] = ent
        h["n_front"] = float(n_front)
        h["front_share"] = float(share)
        # 単騎逃げ: 自分だけが明確な先行型
        h["lone_leader"] = 1.0 if (n_front == 1 and h.get("fpf") is not None
                                   and h["fpf"] <= 0.35) else 0.0


def add_epop(hs):
    """予想人気: 近走平均着順(ar)のレース内昇順順位（1=最有力）。ar欠損は最下位側。"""
    order = sorted(range(len(hs)),
                   key=lambda i: (hs[i].get("ar") is None,
                                  hs[i].get("ar") if hs[i].get("ar") is not None else 99))
    for r, i in enumerate(order):
        hs[i]["epop"] = float(r + 1)


def load():
    Xtr, ytr, gtr, wtr, Xho, yho, gho, ho_races = [], [], [], [], [], [], [], []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            try:
                rc = json.loads(line)
            except json.JSONDecodeError:
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            if MAXDATE and rc["d"] >= MAXDATE:
                continue
            fn = len(hs)
            if _epop:
                add_epop(hs)
            if _relfeat:
                add_rel(hs)
            feats = [[fval(h, rc, k) for k in FEATS] for h in hs]
            # 相対性（LTR）: 着順を上位ほど高い relevance に。1着=fn ... 最下位=1
            rel = [max(0, fn - int(h["rk"]) + 1) for h in hs]
            if rc["d"] < SPLIT:
                Xtr += feats; ytr += rel; gtr.append(fn)
                if _decay:
                    # 経過年 = SPLITからの遡り。古いほど軽く（行単位の重み）
                    yrs = (int(SPLIT[:4]) - int(rc["d"][:4])) \
                        + (int(SPLIT[4:6]) - int(rc["d"][4:6])) / 12.0
                    wtr += [0.5 ** (max(0.0, yrs) / _decay)] * fn
            else:
                Xho += feats; yho += rel; gho.append(fn)
                ho_races.append(rc)
    return (np.array(Xtr, float), np.array(ytr), gtr,
            (np.array(wtr, float) if _decay else None),
            np.array(Xho, float), np.array(yho), gho, ho_races)


def main():
    print("読み込み中…", flush=True)
    Xtr, ytr, gtr, wtr, Xho, yho, gho, ho = load()
    print(f"train {len(gtr):,}R / holdout {len(gho):,}R / 特徴量 {len(FEATS)}"
          + (f" / 減衰半減期{_decay}年" if _decay else "")
          + (" / epop有" if _epop else ""), flush=True)

    dtrain = lgb.Dataset(Xtr, label=ytr, group=gtr, weight=wtr, feature_name=FEATS,
                         categorical_feature=(CAT_FEATS or "auto"))
    dval = lgb.Dataset(Xho, label=yho, group=gho, reference=dtrain)
    # ★ハイパラは環境変数で上書き可（既定=従来値）。選抜はLTR_SPLIT/MAXDATEの2022検証で★
    params = {
        "objective": "lambdarank", "metric": "ndcg", "ndcg_eval_at": [1, 3],
        "learning_rate": float(os.environ.get("LTR_LR", "0.05")),
        "num_leaves": int(os.environ.get("LTR_LEAVES", "31")),
        "min_data_in_leaf": int(os.environ.get("LTR_MINLEAF", "100")),
        "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
        "label_gain": [2 ** i - 1 for i in range(30)], "verbose": -1,
        # ★アンサンブル検証用★ 乱数シードだけ変えたモデルを平均して
        #   分散低減の伸びしろがあるか測る（8モデル構成の設計判断の前に）
        "seed": int(os.environ.get("LTR_SEED", "42")),
    }
    rounds = int(os.environ.get("LTR_ROUNDS", "400"))
    booster = lgb.train(params, dtrain, num_boost_round=rounds, valid_sets=[dval],
                        callbacks=[lgb.log_evaluation(max(50, rounds // 8))])

    class M:
        def predict(self, X): return booster.predict(X)
    model = M()

    # holdout 評価: モデルの◎(=最高スコア)の複勝率・ROI を市場(1番人気)と並べる
    pos = 0
    m_n = m_win = m_top3 = 0
    m_tan = m_fuku = 0
    k_win = k_top3 = k_n = 0
    for rc in ho:
        hs = [h for h in rc["h"] if h.get("rk") is not None]
        n = len(hs)
        X = np.array([[fval(h, rc, k) for k in FEATS] for h in hs], float)
        s = model.predict(X)
        top = hs[int(np.argmax(s))]
        pay = rc.get("pay") or {}
        u = str(int(top["n"]))
        rk = int(top["rk"])
        m_n += 1
        m_win += rk == 1
        m_top3 += rk <= 3

        # 払戻の引き当て。tan/fuku は dict {馬番:円} か list [[馬番,円,人気],...] の両形式あり
        def payof(book):
            if isinstance(book, dict):
                return int(book.get(u, 0) or 0)
            if isinstance(book, list):
                for it in book:
                    if isinstance(it, list) and it and str(int(it[0])) == u:
                        return int(it[1])
            return 0
        m_fuku += payof(pay.get("fuku"))
        m_tan += payof(pay.get("tan"))
        # 市場（1番人気）の複勝率
        fav = None
        for h in hs:
            if h.get("pop") == 1:
                fav = h; break
        if fav:
            k_n += 1
            k_win += int(fav["rk"]) == 1
            k_top3 += int(fav["rk"]) <= 3

    def pct(a, b):
        return 100 * a / b if b else 0
    print("\n=== holdout 実測（LTRの◎ vs 市場1番人気）===")
    print(f"LTRの◎    複勝率 {pct(m_top3,m_n):.1f}%  勝率 {pct(m_win,m_n):.1f}%  "
          f"単ROI {pct(m_tan,100*m_n):.1f}%  複ROI {pct(m_fuku,100*m_n):.1f}%  ({m_n:,}R)")
    print(f"1番人気    複勝率 {pct(k_top3,k_n):.1f}%  勝率 {pct(k_win,k_n):.1f}%")

    booster.save_model(OUT)
    print(f"\n出力: {os.path.relpath(OUT, ROOT)}（木 {booster.num_trees()}本）")
    imp = sorted(zip(FEATS, booster.feature_importance()), key=lambda x: -x[1])
    print("特徴量の重要度:", " ".join(f"{k}:{v}" for k, v in imp[:8]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
