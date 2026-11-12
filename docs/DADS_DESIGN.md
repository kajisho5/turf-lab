# デジタル庁デザインシステム(DADS) リファレンス

**用途**: SEVENTHWELLのアプリ/サイト開発時のデザイン基準。UIを作る・直す時はまずこれを参照。
**出典**: design.digital.go.jp/dads/（β版 v2.16.0）／ドキュメントMD 2026-07-15版／design-tokens npm v2.0.1
**再取得**: docs→ https://design.digital.go.jp/dads/dads-markdown-20260715.zip ／ トークン→ npm @digital-go-jp/design-tokens（dist/tokens.css）
**ライセンス**: 公開リソース。イラスト・アイコン素材は専用利用規約あり。

---

## 1. カラートークン（実値・全パレット）

### プリミティブカラー
各色 50(最淡)〜1200(最濃) の13段階。**テキストは背景と4.5:1以上のコントラスト必須**（DADSは大テキスト例外を採用せず全サイズ4.5:1）。

**blue**: 50:`#e8f1fe` / 100:`#d9e6ff` / 200:`#c5d7fb` / 300:`#9db7f9` / 400:`#7096f8` / 500:`#4979f5` / 600:`#3460fb` / 700:`#264af4` / 800:`#0031d8` / 900:`#0017c1` / 1000:`#00118f` / 1100:`#000071` / 1200:`#000060`

**light-blue**: 50:`#f0f9ff` / 100:`#dcf0ff` / 200:`#c0e4ff` / 300:`#97d3ff` / 400:`#57b8ff` / 500:`#39abff` / 600:`#008bf2` / 700:`#0877d7` / 800:`#0066be` / 900:`#0055ad` / 1000:`#00428c` / 1100:`#00316a` / 1200:`#00234b`

**cyan**: 50:`#e9f7f9` / 100:`#c8f8ff` / 200:`#99f2ff` / 300:`#79e2f2` / 400:`#2bc8e4` / 500:`#01b7d6` / 600:`#00a3bf` / 700:`#008da6` / 800:`#008299` / 900:`#006f83` / 1000:`#006173` / 1100:`#004c59` / 1200:`#003741`

**green**: 50:`#e6f5ec` / 100:`#c2e5d1` / 200:`#9bd4b5` / 300:`#71c598` / 400:`#51b883` / 500:`#2cac6e` / 600:`#259d63` / 700:`#1d8b56` / 800:`#197a4b` / 900:`#115a36` / 1000:`#0c472a` / 1100:`#08351f` / 1200:`#032213`

**lime**: 50:`#ebfad9` / 100:`#d0f5a2` / 200:`#c0f354` / 300:`#ade830` / 400:`#9ddd15` / 500:`#8cc80c` / 600:`#7eb40d` / 700:`#6fa104` / 800:`#618e00` / 900:`#507500` / 1000:`#3e5a00` / 1100:`#2c4100` / 1200:`#1e2d00`

**yellow**: 50:`#fbf5e0` / 100:`#fff0b3` / 200:`#ffe380` / 300:`#ffd43d` / 400:`#ffc700` / 500:`#ebb700` / 600:`#d2a400` / 700:`#b78f00` / 800:`#a58000` / 900:`#927200` / 1000:`#806300` / 1100:`#6e5600` / 1200:`#604b00`

**orange**: 50:`#ffeee2` / 100:`#ffdfca` / 200:`#ffc199` / 300:`#ffa66d` / 400:`#ff8d44` / 500:`#ff7628` / 600:`#fb5b01` / 700:`#e25100` / 800:`#c74700` / 900:`#ac3e00` / 1000:`#8b3200` / 1100:`#6d2700` / 1200:`#541e00`

**red**: 50:`#fdeeee` / 100:`#ffdada` / 200:`#ffbbbb` / 300:`#ff9696` / 400:`#ff7171` / 500:`#ff5454` / 600:`#fe3939` / 700:`#fa0000` / 800:`#ec0000` / 900:`#ce0000` / 1000:`#a90000` / 1100:`#850000` / 1200:`#620000`

**magenta**: 50:`#f3e5f4` / 100:`#ffd0ff` / 200:`#ffaeff` / 300:`#ff8eff` / 400:`#f661f6` / 500:`#f137f1` / 600:`#db00db` / 700:`#c000c0` / 800:`#aa00aa` / 900:`#8b008b` / 1000:`#6c006c` / 1100:`#500050` / 1200:`#3b003b`

**purple**: 50:`#f1eafa` / 100:`#ecddff` / 200:`#ddc2ff` / 300:`#cda6ff` / 400:`#bb87ff` / 500:`#a565f8` / 600:`#8843e1` / 700:`#6f23d0` / 800:`#5c10be` / 900:`#5109ad` / 1000:`#41048e` / 1100:`#30016c` / 1200:`#21004b`

### ニュートラルカラー
**white/black + solid-gray**: white:`#ffffff` / black:`#000000` / 50:`#f2f2f2` / 100:`#e6e6e6` / 200:`#cccccc` / 300:`#b3b3b3` / 400:`#999999` / 420:`#949494` / 500:`#7f7f7f` / 536:`#767676` / 600:`#666666` / 700:`#4d4d4d` / 800:`#333333` / 900:`#1a1a1a`

**opacity-gray（黒の透過）**: 50:`rgba(0, 0, 0, 0.05)` / 100:`rgba(0, 0, 0, 0.1)` / 200:`rgba(0, 0, 0, 0.2)` / 300:`rgba(0, 0, 0, 0.3)` / 400:`rgba(0, 0, 0, 0.4)` / 420:`rgba(0, 0, 0, 0.42)` / 500:`rgba(0, 0, 0, 0.5)` / 536:`rgba(0, 0, 0, 0.54)` / 600:`rgba(0, 0, 0, 0.6)` / 700:`rgba(0, 0, 0, 0.7)` / 800:`rgba(0, 0, 0, 0.8)` / 900:`rgba(0, 0, 0, 0.9)`

### セマンティックカラー（意味→プリミティブ参照）
- `--color-semantic-success-1` → green-600
- `--color-semantic-success-2` → green-800
- `--color-semantic-error-1` → red-800
- `--color-semantic-error-2` → red-900
- `--color-semantic-warning-yellow-1` → yellow-700
- `--color-semantic-warning-yellow-2` → yellow-900
- `--color-semantic-warning-orange-1` → orange-600
- `--color-semantic-warning-orange-2` → orange-800

---

## 2. タイポグラフィ

**フォント**: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif（等幅: Noto Sans Mono）
**ウェイト**: N=400 / B=700 の2段のみ
**サイズ段階(px)**: 14,16,17,18,20,22,24,26,28,32,36,45,48,57,64

**サイズの使い分け**:
- 48〜64: 視覚的インパクト用（Display）
- 16〜45: 見出し・本文。**本文/UIは16px以上が基準**
- 14: 例外用途のみ（フッター等）。**14px未満は原則禁止**

**行間(line-height)の使い分け**:
- 100%: ボタン等ワンライン ／ 120-130%: 管理画面など情報密度優先
- 140%: 見出し ／ 150%: 本文の最低限度 ／ 160-175%: 一般的な本文（推奨は1.5倍以上）

**トークン命名**: `Std-17N-170` = Standardスタイル・17px・Normal・行間170%

---

## 3. 角丸・エレベーション

**border-radius**: 4=0.25rem, 6=0.375rem, 8=0.5rem, 12=0.75rem, 16=1rem, 24=1.5rem, 32=2rem, full=624.9375rem

**elevation(影)** 1〜8段:
- `elevation-1`: 0 2px 8px 1px rgba(0,0,0,0.1), 0 1px 5px 0 rgba(0,0,0,0.3)
- `elevation-2`: 0 2px 12px 2px rgba(0,0,0,0.1), 0 1px 6px 0 rgba(0,0,0,0.3)
- `elevation-3`: 0 4px 16px 3px rgba(0,0,0,0.1), 0 1px 6px 0 rgba(0,0,0,0.3)
- `elevation-4`: 0 6px 20px 4px rgba(0,0,0,0.1), 0 2px 6px 0 rgba(0,0,0,0.3)
- `elevation-5`: 0 8px 24px 5px rgba(0,0,0,0.1), 0 2px 10px 0 rgba(0,0,0,0.3)
- `elevation-6`: 0 10px 30px 6px rgba(0,0,0,0.1), 0 3px 12px 0 rgba(0,0,0,0.3)
- `elevation-7`: 0 12px 36px 7px rgba(0,0,0,0.1), 0 3px 14px 0 rgba(0,0,0,0.3)
- `elevation-8`: 0 14px 40px 7px rgba(0,0,0,0.1), 0 3px 16px 0 rgba(0,0,0,0.3)

---

## 4. レイアウト
- ブレークポイントは基本**1つ**: モバイル/タブレット=768px未満、デスクトップ=768px以上
- スペーシングの専用トークンは無し（8の倍数ベースの余白設計が作例の慣例）

---

## 5. コンポーネント一覧（50種、各ガイドラインは docs zip の components/<name>/index.md）
accordion, blockquote, bottom-navigation, breadcrumb, button, card, carousel, checkbox,
chip-label, chip-tag, combobox, date-picker, description-list, disclosure, divider, drawer,
emergency-banner, file-upload, hamburger-menu-button, header-container, heading,
horizontal-menu, image, image-slider, input-text, language-selector, list, mega-menu,
menu-list, menu-list-box, mobile-menu, modal-dialog, notice-block, notification-banner,
page-navigation, progress-indicator, radio, resource-list, scroll-top-button, search-box,
select, step-navigation, switch, tab, table, table-control, textarea, toc, utility-link

---

## 6. アクセシビリティ要点（JIS X 8341-3 / WCAG 2.1-2.2準拠）
- **コントラスト**: テキスト・文字画像は背景に対し**常に4.5:1以上**（サイズによる緩和なし）
- 本文・UIテキストは16px以上、14px未満禁止
- フォーカスインジケータ必須（キーボード操作可能に）
- エラーは色だけで伝えない（アイコン+テキスト併用）

---

## 7. 実装リソース

**配布元(まずここを見る)**: https://design.digital.go.jp/dads/resources/
　※このMDの内容はここで配布されている「2026年7月15日版」ドキュメントzipに基づく（2026-07-19 時点で最新）。
　　更新確認はこのページの配布zipの日付を見るのが早い。

- HTML版スニペット: github.com/digital-go-jp/design-system-example-components-html （Storybook: design.digital.go.jp/dads/html/）
- React版(Tailwind): github.com/digital-go-jp/design-system-example-components-react （Storybook: /dads/react/）
- Tailwindテーマ: github.com/digital-go-jp/tailwind-theme-plugin
- トークンCSS: `@digital-go-jp/design-tokens` → dist/tokens.css（CSS変数として全定義。このMDの§1,3はここから機械抽出）
- **デザインデータ(Figma)**: Figma Communityで公開。v2系統が現行（v1系統はエラー修正のみ）。Figmaの無料アカウントが要る。
- **イラスト・アイコン素材**: 行政手続きの説明用に作られたもの。専用の利用規約の範囲で無料利用可。
  → SW TURF LAB（競馬・営利寄り）で使う場合は用途が規約に収まるか要確認。トークンや原則の流用と違い、素材は規約の対象。
- **ウェブアクセシビリティ導入ガイドブック**: デジタル庁公開の初級者向け資料。
- 調達等で特定バージョンの指定が要る場合は個別対応の窓口あり。

---

## 8. SW系プロジェクトへの適用メモ
- ダークテーマ主体のSW TURF LABにそのまま色を移植する必要は無い。**使うべきは原則の方**:
  4.5:1コントラスト／本文16px+／行間1.5／N・Bの2ウェイト／意味色（error=red-800系, success=green-600系）の一貫性
- 公共向け・ライトテーマの新規サイトを作る時はDADSのトークン+Reactスニペットをそのまま採用するのが最速
