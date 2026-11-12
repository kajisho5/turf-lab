# -*- coding: utf-8 -*-
"""公開サイトの置き場所を1箇所にまとめる

★なぜ要るか★
  OGPの og:url / og:image は**絶対URLでないと効かない**（Xがカードを出せない）。
  そのため各ページにドメインを直書きしていたが、それだとドメインを移した瞬間に
  全ページのカードが壊れる。移設コストを0にするためにここへ集約する。

  ページ内のリンクは相対にしてあるので、ここを差し替えるだけで移設できる。

サイトは2つある:
  public   : kajikeiba.com          フォロワー向け（広告・データ記事）
  legacy   : seventh-well.com/odds/ これまでの置き場。当面は残す
"""

SITES = {
    "public": {
        "base": "https://kajikeiba.com",          # 末尾スラッシュ無し
        "remote": "/kajikeiba.com",               # FTP上のドキュメントルート
        "name": "カジ競馬",
        "twitter": "@kaji_keiba",
        "ads": True,                              # 広告枠を出すか
    },
    "legacy": {
        "base": "https://seventh-well.com/odds",
        "remote": "/seventh-well.com/odds",
        "name": "SW TURF LAB",
        "twitter": "@kaji_keiba",
        "ads": False,
    },
}

# Google AdSense。全ページの先頭で読み込む。
# ★ここも1箇所にまとめる★ ページごとに貼ると、貼り忘れ・publish IDの食い違いが起きる。
ADSENSE_CLIENT = "ca-pub-2591053009962162"
ADSENSE_TAG = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    f'?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>'
)

DEFAULT = "public"


def get(name=None):
    return SITES[name or DEFAULT]


def url(path, site=None):
    """サイト内パス（先頭スラッシュ無し）を絶対URLにする"""
    s = get(site)
    return f"{s['base']}/{path.lstrip('/')}" if path else s["base"] + "/"


import hashlib as _hashlib
import os as _os

_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))


def asset(path):
    """core/ の共通資産にバージョンを付ける

    ★なぜ要るか★
      theme.css に縞模様の定義を足してデプロイしたのに、ブラウザが
      古いCSSを持ち続けて反映されなかった（--stripe が空のまま）。
      サーバーには新しいものがあるのに画面が変わらない、という
      一番気づきにくい状態になる。
      中身のハッシュを付けておけば、変わったときだけURLが変わる。
    """
    f = _os.path.join(_ROOT, path.lstrip("/"))
    try:
        h = _hashlib.sha256(open(f, "rb").read()).hexdigest()[:8]
    except OSError:
        h = "0"
    return f"/{path.lstrip('/')}?v={h}"


def adsense(site=None):
    """広告タグ。public サイトだけに出す（運営用・知人向けには出さない）"""
    return (ADSENSE_TAG + chr(10)) if get(site)["ads"] else ""


def ad_slot(where, site=None):
    """広告枠。ASPのタグを貰ったら SLOT の中身を差し替えるだけで有効になる。

    ★いまは何も出さない（枠だけ）★
      審査前に空タグを置いても表示されないので、コメントで位置を明示しておく。
      タグを入れる時は <!-- AD:START --> と <!-- AD:END --> の間に貼る。
    """
    if not get(site)["ads"]:
        return ""
    return (f'\n<div class="ad" data-slot="{where}">'
            f'<!-- AD:START {where} -->'
            f'<!-- ここにASPから貰った広告タグを貼る。貼るまで何も表示されない -->'
            f'<!-- AD:END {where} --></div>\n')
