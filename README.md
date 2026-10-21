# WorldInJapan データ収集

世界銀行 Open Data API から国別・年別の指標を取得し、`data/` に CSV として保存するコレクターです。

## 構成

- `collect_worldbank.py` — 取得スクリプト（Python 3.8+、外部ライブラリ不要）
- `.github/workflows/collect.yml` — GitHub Actions で毎月1日・15日に自動実行し、更新があれば `data/` をコミット
- `data/` — 出力先（初回実行で作られる）

## 手元で実行する

```
python3 collect_worldbank.py                 # 全指標
python3 collect_worldbank.py --only SP.POP.TOTL,NY.GDP.PCAP.CD
```

22指標 × 約217か国 × 1960年〜 で、全体で数分かかります。

## 出力ファイル

| ファイル | 内容 |
|---|---|
| `data/countries.csv` | 国コード(ISO3)・国名・地域・所得区分。World/EU などの集計地域は除外済み |
| `data/indicators.csv` | 取得した指標の一覧（日本語名・カテゴリ・英語名・出典・行数・年範囲） |
| `data/<指標コード>.csv` | `country_code,year,value`。値の無い年は含まない |
| `data/manifest.json` | 取得日時、指標ごとの行数・最終データ年、失敗した指標 |

## 指標を追加する

`collect_worldbank.py` の `INDICATORS` に `"コード": ("日本語名", "カテゴリ")` を追加するだけです。
コードは https://data.worldbank.org/indicator で検索できます。

## GitHub Actions で動かす

1. このフォルダを GitHub リポジトリとして push する（public でも private でも可）
2. リポジトリの Settings → Actions → General → Workflow permissions を **Read and write** にする
3. Actions タブ → "Collect World Bank data" → **Run workflow** で初回を手動実行
4. 以後は毎月1日・15日 12:17（日本時間）に自動実行

## ライセンス

データは World Bank Open Data（CC BY 4.0）。サイトで公開する際は
「出典: The World Bank, World Development Indicators」の表記が必要です。
世界銀行のロゴ使用や「世界銀行公認」といった表現は不可。
