#!/usr/bin/env python3
"""
世界の中の日本 ── 静的サイト生成（data/ → site/）

使い方:
  SITE_URL=https://worldinjapan.pages.dev python3 build_site.py
  python3 build_site.py --links index     # 「…/index.html」形式のリンク（プレビュー用）

入力: data/（collect_worldbank.py の出力）, web/（style.css, app.js, countries_ja.json, monetize.json）
出力: site/ … そのまま静的ホスティングに置ける
標準ライブラリのみ。
"""
import argparse
import csv
import html
import json
import os
import shutil
from datetime import datetime, timezone

SITE_NAME = "世界の中の日本"
TAGLINE = "データで見る、日本の強みと弱み"
RECENT_YEARS = 5  # 指標の最新年からこの年数以内の値をランキングに使う
# グラフ用ライブラリ。上から順に試し、読めなければ次へ（最後は同じサイトに置いた控え web/echarts.min.js）
CHARTS_JS = [
    "https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.1/echarts.min.js",
    "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js",
]

GROUPS = {
    "oecd": ("OECD加盟国", ["AUS", "AUT", "BEL", "CAN", "CHL", "COL", "CRI", "CZE", "DNK", "EST", "FIN", "FRA",
                          "DEU", "GRC", "HUN", "ISL", "IRL", "ISR", "ITA", "JPN", "KOR", "LVA", "LTU", "LUX",
                          "MEX", "NLD", "NZL", "NOR", "POL", "PRT", "SVK", "SVN", "ESP", "SWE", "CHE", "TUR",
                          "GBR", "USA"]),
    "g7": ("G7", ["JPN", "USA", "DEU", "GBR", "FRA", "ITA", "CAN"]),
    "asia": ("アジア主要国", ["JPN", "CHN", "KOR", "IND", "IDN", "THA", "VNM", "SGP", "MYS", "PHL", "HKG"]),
    "world": ("全世界", None),
}
GROUP_ORDER = ["oecd", "g7", "asia", "world"]
DEFAULT_GROUP = "oecd"
REGION_JA = {
    "East Asia & Pacific": "東アジア・太平洋",
    "Europe & Central Asia": "ヨーロッパ・中央アジア",
    "Latin America & Caribbean": "中南米・カリブ",
    "Middle East, North Africa, Afghanistan & Pakistan": "中東・北アフリカ",
    "North America": "北米",
    "South Asia": "南アジア",
    "Sub-Saharan Africa": "サハラ以南アフリカ",
}
INCOME_JA = {"High income": "高所得国", "Upper middle income": "上位中所得国",
             "Lower middle income": "下位中所得国", "Low income": "低所得国"}
COMPARE_DEFAULT = ["JPN", "USA", "DEU", "GBR", "KOR", "CHN"]

# (分野名, slug, 本の検索語)
CATEGORIES = [
    ("経済", "economy", "日本経済"),
    ("労働", "labor", "日本の労働"),
    ("財政", "fiscal", "日本の財政"),
    ("貿易", "trade", "日本の貿易"),
    ("国際収支", "balance-of-payments", "国際収支"),
    ("為替", "exchange", "円安"),
    ("人口", "population", "人口減少"),
    ("保健", "health", "日本の医療"),
    ("教育", "education", "日本の教育"),
    ("技術", "technology", "日本の技術力"),
    ("環境", "environment", "日本の環境問題"),
    ("エネルギー", "energy", "日本のエネルギー"),
    ("ジェンダー", "gender", "ジェンダー 日本"),
    ("格差", "inequality", "日本の格差"),
    ("安全", "safety", "日本の治安"),
    ("安全保障", "defense", "日本の安全保障"),
    ("観光", "tourism", "インバウンド"),
]
CAT_SLUG = {c[0]: c[1] for c in CATEGORIES}

# 指標の表示設定
#   dir: 1=高いほど良い, -1=低いほど良い, 0=良し悪しをつけない（強み・弱みの判定に使わない）
#   fmt: money（兆・億ドル）, pop（億・万人）, count（万＋単位）, num（桁数 d ＋単位 u）
#   rank: False のものは国の間の順位をつけない（通貨単位が国ごとに違う等）
M = {}


def ind(code, slug, cat, name, desc, dir=0, fmt="num", d=1, u="", rank=True):
    M[code] = dict(code=code, slug=slug, cat=cat, name=name, desc=desc, dir=dir, fmt=fmt, d=d, u=u, rank=rank)


ind("NY.GDP.MKTP.CD", "gdp", "経済", "GDP（名目・米ドル換算）",
    "国内総生産（GDP）を各年の為替レートで米ドルに換算した値。経済の規模を表すが、為替の変動に大きく左右される。", 0, "money")
ind("NY.GDP.PCAP.CD", "gdp-per-capita", "経済", "一人当たりGDP（名目）",
    "GDPを人口で割った一人当たりの値（米ドル換算）。為替レートの影響を受けるため、円安の年は日本の値が小さくなる。", 1, "num", 0, "ドル")
ind("NY.GDP.PCAP.PP.CD", "gdp-per-capita-ppp", "経済", "一人当たりGDP（購買力平価）",
    "物価の違いをならす購買力平価で換算した一人当たりGDP（国際ドル）。生活水準の比較に向く。", 1, "num", 0, "国際ドル")
ind("NY.GDP.MKTP.KD.ZG", "gdp-growth", "経済", "実質GDP成長率",
    "物価変動の影響を除いた実質GDPの前年比の伸び率。", 1, "num", 1, "%")
ind("FP.CPI.TOTL.ZG", "inflation", "経済", "消費者物価上昇率",
    "消費者物価指数の前年比の上昇率。高すぎても低すぎても問題とされるため、良し悪しはつけていない。", 0, "num", 1, "%")
ind("NV.IND.MANF.ZS", "manufacturing", "経済", "製造業の付加価値（対GDP比）",
    "製造業が生み出した付加価値がGDPに占める割合。", 0, "num", 1, "%")
ind("SL.UEM.TOTL.ZS", "unemployment", "労働", "失業率",
    "労働力人口に占める失業者の割合（ILOのモデル推計）。各国の公式統計と値が異なることがある。", -1, "num", 1, "%")
ind("GC.DOD.TOTL.GD.ZS", "government-debt", "財政", "中央政府の債務残高（対GDP比）",
    "中央政府の債務残高の対GDP比。国によって集計の範囲が異なり、日本は世界銀行のデータに含まれていない。", -1, "num", 1, "%")
ind("GC.TAX.TOTL.GD.ZS", "tax-revenue", "財政", "税収（対GDP比）",
    "中央政府の税収の対GDP比。日本は1990年代半ば以降のデータがない。", 0, "num", 1, "%")
ind("NE.EXP.GNFS.ZS", "exports", "貿易", "輸出（対GDP比）",
    "財・サービスの輸出額の対GDP比。経済がどれだけ海外の需要に支えられているかの目安。", 0, "num", 1, "%")
ind("TX.VAL.TECH.MF.ZS", "high-tech-exports", "貿易", "ハイテク製品の輸出比率",
    "工業製品の輸出に占めるハイテク製品（航空宇宙・医薬品・電子機器など研究開発の比重が高い製品）の割合。", 1, "num", 1, "%")
ind("BN.CAB.XOKA.GD.ZS", "current-account", "国際収支", "経常収支（対GDP比）",
    "貿易・サービス・投資収益などをまとめた経常収支の対GDP比。プラスは黒字。", 0, "num", 1, "%")
ind("BX.KLT.DINV.WD.GD.ZS", "fdi-inflows", "国際収支", "対内直接投資（対GDP比）",
    "海外からの直接投資の純流入額の対GDP比。", 1, "num", 1, "%")
ind("FI.RES.TOTL.CD", "reserves", "国際収支", "外貨準備（金を含む）",
    "金を含む外貨準備の総額（米ドル）。", 0, "money")
ind("DERIVED.PRICE_LEVEL", "price-level", "為替", "物価水準（米国＝1）",
    "購買力平価を為替レートで割った値。米国の物価を1としたときの物価水準の目安で、1より小さいほどドルで見て物価が安い。", 0, "num", 2, "")
ind("PA.NUS.FCRF", "exchange-rate", "為替", "対ドル為替レート（年平均）",
    "自国通貨の対米ドル為替レートの年平均。日本は1ドルあたりの円。通貨ごとに単位が違うため、国の間の順位はつけていない。", 0, "num", 1, "", False)
ind("PA.NUS.PPP", "ppp", "為替", "購買力平価（GDP）",
    "1国際ドル（米国での1ドル分の購買力）に相当する自国通貨の額。日本は円。通貨ごとに単位が違うため、国の間の順位はつけていない。", 0, "num", 1, "", False)
ind("SP.POP.TOTL", "population", "人口", "総人口",
    "年央の総人口。", 0, "pop")
ind("SP.POP.GROW", "population-growth", "人口", "人口増加率",
    "総人口の前年比の増減率。", 0, "num", 2, "%")
ind("SP.DYN.TFRT.IN", "fertility-rate", "人口", "合計特殊出生率",
    "一人の女性が生涯に産む子どもの数の推計。人口を維持できる水準はおよそ2.1とされる。", 0, "num", 2, "")
ind("SP.POP.65UP.TO.ZS", "aged-65", "人口", "65歳以上の人口の割合",
    "総人口に占める65歳以上の人の割合。", 0, "num", 1, "%")
ind("SP.URB.TOTL.IN.ZS", "urban-population", "人口", "都市に住む人の割合",
    "都市部に住む人の割合。都市の定義は国ごとに異なる。", 0, "num", 1, "%")
ind("SP.DYN.LE00.IN", "life-expectancy", "保健", "平均寿命",
    "出生時の平均余命（男女計）。", 1, "num", 1, "歳")
ind("SP.DYN.IMRT.IN", "infant-mortality", "保健", "乳児死亡率",
    "1歳未満で亡くなる乳児の数（出生1,000人あたり）。", -1, "num", 1, "人")
ind("SH.MED.PHYS.ZS", "physicians", "保健", "医師の数（人口1,000人あたり）",
    "人口1,000人あたりの医師の数。", 1, "num", 2, "人")
ind("SH.XPD.CHEX.GD.ZS", "health-expenditure", "保健", "医療支出（対GDP比）",
    "公的・民間を合わせた経常医療支出の対GDP比。", 0, "num", 1, "%")
ind("SE.XPD.TOTL.GD.ZS", "education-expenditure", "教育", "公的教育支出（対GDP比）",
    "政府の教育支出の対GDP比。家計などの私費負担は含まない。", 0, "num", 1, "%")
ind("SE.TER.ENRR", "tertiary-enrollment", "教育", "高等教育の就学率",
    "大学など高等教育の総就学率（該当する年齢の人口に対する在籍者の割合）。年齢外の学生を含むため100%を超えることがある。", 1, "num", 1, "%")
ind("GB.XPD.RSDV.GD.ZS", "rd-expenditure", "技術", "研究開発費（対GDP比）",
    "企業・政府・大学などの研究開発費の合計の対GDP比。", 1, "num", 2, "%")
ind("SP.POP.SCIE.RD.P6", "researchers", "技術", "研究者の数（人口100万人あたり）",
    "研究開発に従事する研究者の数（人口100万人あたり）。", 1, "num", 0, "人")
ind("IP.PAT.RESD", "patent-applications", "技術", "特許出願数（居住者）",
    "その国に住む人・企業による特許の出願件数。", 0, "count", 1, "件")
ind("IT.NET.USER.ZS", "internet-users", "技術", "インターネット利用率",
    "過去3か月にインターネットを利用した人の割合。", 1, "num", 1, "%")
ind("EN.GHG.CO2.PC.CE.AR5", "co2-per-capita", "環境", "一人当たりCO2排出量",
    "一人当たりの二酸化炭素排出量（土地利用によるものを除く）。", -1, "num", 2, "トン")
ind("EG.FEC.RNEW.ZS", "renewable-energy", "環境", "再生可能エネルギーの割合",
    "最終エネルギー消費に占める再生可能エネルギーの割合。薪などの伝統的なバイオマスも含むため、途上国で高く出やすい。", 1, "num", 1, "%")
ind("AG.LND.FRST.ZS", "forest-area", "環境", "森林の割合",
    "国土の面積に占める森林の割合。", 0, "num", 1, "%")
ind("EG.IMP.CONS.ZS", "energy-imports", "エネルギー", "エネルギーの輸入依存度",
    "エネルギー消費量に対する純輸入量の割合。高いほど海外のエネルギーに頼っている。マイナスは輸出国。", -1, "num", 1, "%")
ind("EG.USE.PCAP.KG.OE", "energy-use", "エネルギー", "一人当たりエネルギー消費",
    "一人当たりの一次エネルギー消費量（石油換算）。", 0, "num", 0, "kg")
ind("SL.TLF.CACT.FE.ZS", "female-labor", "ジェンダー", "女性の労働参加率",
    "15歳以上の女性のうち、働いているか仕事を探している人の割合（ILOのモデル推計）。", 1, "num", 1, "%")
ind("SG.GEN.PARL.ZS", "women-in-parliament", "ジェンダー", "女性国会議員の割合",
    "国会（下院または一院制の議会）の議席に占める女性の割合。", 1, "num", 1, "%")
ind("SI.POV.GINI", "gini", "格差", "ジニ係数",
    "所得または消費の分配の不平等さを0〜100で表す指数。高いほど格差が大きい。調査年が国ごとにまちまち。", -1, "num", 1, "")
ind("VC.IHR.PSRC.P5", "homicide-rate", "安全", "殺人の発生率",
    "故意の殺人の被害者の数（人口10万人あたり）。", -1, "num", 2, "人")
ind("MS.MIL.XPND.GD.ZS", "military-expenditure", "安全保障", "軍事支出（対GDP比）",
    "軍事支出の対GDP比（ストックホルム国際平和研究所の推計）。", 0, "num", 2, "%")
ind("ST.INT.ARVL", "tourist-arrivals", "観光", "外国人旅行者数",
    "海外から入国した旅行者の数。世界銀行のデータは2020年で更新が止まっており、コロナ禍の影響を受けた値になっている。", 0, "count", 1, "人")
ind("ST.INT.RCPT.CD", "tourism-receipts", "観光", "国際観光収入",
    "海外からの旅行者による支出（米ドル）。2020年で更新が止まっている。", 0, "money")


# ---------------------------------------------------------------- 書式

def fmt_value(m, v):
    if v is None:
        return "—"
    f = m["fmt"]
    if f == "money":
        a = abs(v)
        if a >= 1e12:
            return f"{v / 1e12:,.2f}兆ドル"
        if a >= 1e8:
            return f"{v / 1e8:,.0f}億ドル"
        return f"{v / 1e4:,.0f}万ドル"
    if f == "pop":
        if v >= 1e8:
            return f"{v / 1e8:,.2f}億人"
        if v >= 1e4:
            return f"{v / 1e4:,.0f}万人"
        return f"{v:,.0f}人"
    if f == "count":
        if abs(v) >= 1e4:
            return f"{v / 1e4:,.1f}万{m['u']}"
        return f"{v:,.0f}{m['u']}"
    return f"{v:,.{m['d']}f}{m['u']}"


def esc(s):
    return html.escape(str(s), quote=True)


def round_sig(v, sig=5):
    if v == 0:
        return 0
    from math import floor, log10
    return round(v, sig - 1 - int(floor(log10(abs(v)))))


# ---------------------------------------------------------------- データ

def load_series(data_dir, code):
    path = os.path.join(data_dir, f"{code}.csv")
    if not os.path.exists(path):
        return None
    s = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s.setdefault(r["country_code"], {})[int(r["year"])] = float(r["value"])
    return s


def derive_price_level(data_dir):
    ppp = load_series(data_dir, "PA.NUS.PPP")
    fx = load_series(data_dir, "PA.NUS.FCRF")
    if not ppp or not fx:
        return None
    out = {}
    for c, ys in ppp.items():
        for y, v in ys.items():
            x = fx.get(c, {}).get(y)
            if x:
                out.setdefault(c, {})[y] = v / x
    return out


def latest_values(series, max_year):
    """国ごとの最新値 {iso: (year, value)}（max_year - RECENT_YEARS 以降のみ）"""
    out = {}
    for c, ys in series.items():
        y = max(ys)
        if y >= max_year - RECENT_YEARS:
            out[c] = (y, ys[y])
    return out


def ranking(m, latest, members, focus=None):
    """順位表 [(iso, year, value)]。dir=-1 は小さい順、それ以外は大きい順。focus の国はまとまりの外でも加える。"""
    rows = [(c, y, v) for c, (y, v) in latest.items() if members is None or c in members or c == focus]
    rows.sort(key=lambda r: r[2], reverse=(m["dir"] != -1))
    return rows


def order_label(m):
    return "低い順" if m["dir"] == -1 else "高い順"


# ---------------------------------------------------------------- HTML

class Site:
    def __init__(self, out, links, site_url, monetize, names, inline=None):
        self.inline = inline  # {"css": str, "js": str} のとき、CSS・JS・データをページに埋め込む
        self.local_charts = False
        self.out = out
        self.links = links
        self.site_url = site_url.rstrip("/")
        self.mon = monetize
        self.names = names
        self.urls = []

    def href(self, depth, path):
        """path は 'i/gdp/' のようなサイト内パス（'' はトップ）"""
        pre = "/" if depth is None else "../" * depth
        if self.links == "index" and (path == "" or path.endswith("/")):
            path = path + "index.html"
        return pre + path if (pre + path) else "./"

    def write(self, path, title, desc, body, depth, page_type, extra="", data=None):
        url = f"{self.site_url}/{path}"
        self.urls.append(url)
        full_title = title if path == "" else f"{title}｜{SITE_NAME}"
        if path == "" and os.environ.get("SHORT_HOME_TITLE"):
            full_title = SITE_NAME
        ads = ""
        if self.mon.get("adsense_client"):
            ads = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
                   f'{esc(self.mon["adsense_client"])}" crossorigin="anonymous"></script>')
        h = self.href
        support = ""
        if self.mon.get("support_url"):
            support = f'<a class="btn" href="{esc(self.mon["support_url"])}" rel="noopener" target="_blank">応援する</a>'
        if self.inline:
            style_tag = f"<style>{self.inline['css']}</style>"
            app_tag = f"<script>{self.inline['js']}</script>"
            data_tag = ""
            if data:
                payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
                data_tag = f'<script type="application/json" id="wij-data">{payload}</script>\n'
        else:
            style_tag = f'<link rel="stylesheet" href="{h(depth, "assets/style.css")}">'
            app_tag = f'<script src="{h(depth, "assets/app.js")}" defer></script>'
            data_tag = ""
        srcs = list(CHARTS_JS)
        if self.local_charts:
            srcs.append(("/" if depth is None else "../" * depth) + "assets/echarts.min.js")
        charts_loader = ("<script>(function(){var u=" + json.dumps(srcs) + ";function n(i){if(i>=u.length){window.__chartsFailed=true;return;}"
                         "var s=document.createElement('script');s.src=u[i];s.onerror=function(){n(i+1)};document.head.appendChild(s);}n(0);})();</script>")
        doc = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="{'website' if path == '' else 'article'}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{esc(full_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{self.site_url}/og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@600;700&display=swap" rel="stylesheet">
{style_tag}
{ads}
</head>
<body data-page="{page_type}" data-root="{'/' if depth is None else ('../' * depth or './')}" data-links="{self.links}"{extra}>
<header class="site-head">
  <div class="wrap head-inner">
    <a class="logo" href="{h(depth, '')}">{SITE_NAME}</a>
    <nav class="nav">
      <a href="{h(depth, 'i/')}">指標一覧</a>
      <a href="{h(depth, 'c/')}">国から見る</a>
      <a href="{h(depth, 'about/')}">このサイトについて</a>
    </nav>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="site-foot">
  <div class="wrap">
    <p class="foot-title">{SITE_NAME}</p>
    <p>{TAGLINE}。データは世界銀行 World Development Indicators（CC BY 4.0）をもとに、毎月2回自動で更新しています。</p>
    <p><a href="{h(depth, 'about/')}">このサイトについて・出典・広告について</a> {support}</p>
  </div>
</footer>
{charts_loader}
{data_tag}{app_tag}
</body>
</html>
"""
        target = os.path.join(self.out, path, "index.html") if (path == "" or path.endswith("/")) else os.path.join(self.out, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(doc)

    def books(self, kw):
        links = []
        q = esc(kw)
        if self.mon.get("rakuten_affiliate_id"):
            from urllib.parse import quote
            target = f"https://books.rakuten.co.jp/search?sitem={quote(kw)}"
            u = f"https://hb.afl.rakuten.co.jp/hgc/{self.mon['rakuten_affiliate_id']}/?pc={quote(target, safe='')}"
            links.append(f'<a class="btn" href="{esc(u)}" rel="sponsored noopener" target="_blank">楽天ブックスで探す</a>')
        if self.mon.get("amazon_associate_tag"):
            from urllib.parse import quote
            u = f"https://www.amazon.co.jp/s?k={quote(kw)}&i=stripbooks&tag={quote(self.mon['amazon_associate_tag'])}"
            links.append(f'<a class="btn" href="{esc(u)}" rel="sponsored noopener" target="_blank">Amazonで探す</a>')
        if not links:
            return ""
        return f"""<section class="block books"><h2>もっと知る本 <span class="pr">PR</span></h2>
<p class="muted">「{q}」に関する本を探す</p><p>{' '.join(links)}</p></section>"""


def group_tabs(active="oecd", region_label="同じ地域"):
    t = f'<button type="button" class="tab{" on" if active == "region" else ""}" data-group="region">{esc(region_label)}</button>'
    t += "".join(
        f'<button type="button" class="tab{" on" if k == active else ""}" data-group="{k}">{GROUPS[k][0]}</button>'
        for k in GROUP_ORDER)
    return f'<div class="tabs" role="group" aria-label="比べる国のまとまり">{t}</div>'


def jp_sentence(m, latest, members, gname):
    if not m["rank"]:
        j = latest.get("JPN")
        return f"日本は{j[0]}年に{j[1]:,.1f}円。" if j else "日本のデータはありません。"
    rows = ranking(m, latest, members)
    for i, (c, y, v) in enumerate(rows):
        if c == "JPN":
            return f"日本は{y}年に{fmt_value(m, v)}で、{gname}{len(rows)}か国・地域中<strong>{i + 1}位</strong>（{order_label(m)}）。"
    return "日本の最近のデータはありません。"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--web", default="web")
    ap.add_argument("--out", default="site")
    ap.add_argument("--links", choices=["pretty", "index"], default="pretty")
    ap.add_argument("--inline", action="store_true", help="CSS・JS・データを各ページに埋め込む（プレビュー用）")
    ap.add_argument("--countries", default="", help="国のページを作る国（カンマ区切りのISO3。空なら全部）")
    args = ap.parse_args()
    site_url = os.environ.get("SITE_URL", "https://worldinjapan.pages.dev")

    names = json.load(open(os.path.join(args.web, "countries_ja.json"), encoding="utf-8"))
    mon_path = os.path.join(args.web, "monetize.json")
    monetize = json.load(open(mon_path, encoding="utf-8")) if os.path.exists(mon_path) else {}
    manifest = json.load(open(os.path.join(args.data, "manifest.json"), encoding="utf-8"))
    countries = {r["country_code"]: r for r in csv.DictReader(open(os.path.join(args.data, "countries.csv"), encoding="utf-8"))}

    if os.path.exists(args.out):
        shutil.rmtree(args.out)
    os.makedirs(os.path.join(args.out, "data", "i"))
    os.makedirs(os.path.join(args.out, "assets"))
    for f in ("style.css", "app.js", "echarts.min.js"):
        if os.path.exists(os.path.join(args.web, f)):
            shutil.copy(os.path.join(args.web, f), os.path.join(args.out, "assets", f))
    if os.path.exists(os.path.join(args.web, "og.png")):
        shutil.copy(os.path.join(args.web, "og.png"), os.path.join(args.out, "og.png"))

    inline = None
    if args.inline:
        inline = {f.split(".")[1]: open(os.path.join(args.web, f), encoding="utf-8").read() for f in ("style.css", "app.js")}
    S = Site(args.out, args.links, site_url, monetize, names, inline)
    S.local_charts = os.path.exists(os.path.join(args.web, "echarts.min.js"))
    series_json = {}

    # ---- 系列を読み込み、JSON を書き出す
    series, latest_all, maxy = {}, {}, {}
    for code, m in M.items():
        s = derive_price_level(args.data) if code.startswith("DERIVED.") else load_series(args.data, code)
        if not s:
            continue
        series[code] = s
        my = max(max(ys) for ys in s.values())
        maxy[code] = my
        latest_all[code] = latest_values(s, my)
        y0 = min(min(ys) for ys in s.values())
        vals = {c: [round_sig(ys[y]) if y in ys else None for y in range(y0, my + 1)] for c, ys in s.items()}
        series_json[m["slug"]] = {"y0": y0, "v": vals}
        with open(os.path.join(args.out, "data", "i", f"{m['slug']}.json"), "w", encoding="utf-8") as f:
            json.dump(series_json[m["slug"]], f, separators=(",", ":"))

    active = [c for c in M if c in series]
    region_of = {k: v["region"].strip() for k, v in countries.items()}
    wanted = [x.strip().upper() for x in args.countries.split(",") if x.strip()]
    country_pages = sorted(k for k in countries if k != "JPN" and (not wanted or k in wanted)) + ["JPN"]
    meta = {
        "indicators": {M[c]["slug"]: {k: M[c][k] for k in ("code", "name", "cat", "dir", "fmt", "d", "u", "rank")}
                       | {"maxYear": maxy[c]} for c in active},
        "categories": [{"name": n, "slug": s} for n, s, _ in CATEGORIES],
        "groups": {k: {"name": v[0], "members": v[1]} for k, v in GROUPS.items()},
        "groupOrder": GROUP_ORDER,
        "names": names,
        "compareDefault": COMPARE_DEFAULT,
        "regionOf": region_of,
        "regionNames": REGION_JA,
        "countryPages": country_pages,
        "recentYears": RECENT_YEARS,
    }
    with open(os.path.join(args.out, "data", "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
    latest_json = {M[c]["slug"]: {k: [y, round_sig(v)] for k, (y, v) in latest_all[c].items()} for c in active}
    with open(os.path.join(args.out, "data", "latest.json"), "w", encoding="utf-8") as f:
        json.dump(latest_json, f, separators=(",", ":"))

    oecd = set(GROUPS["oecd"][1])
    by_cat = {}
    for c in active:
        by_cat.setdefault(M[c]["cat"], []).append(c)

    # ---- 指標ページ
    for code in active:
        m = M[code]
        lat = latest_all[code]
        depth = 2
        lead = jp_sentence(m, lat, oecd, "OECD加盟国") if m["rank"] else jp_sentence(m, lat, None, "")
        world = ""
        if m["rank"]:
            wr = ranking(m, lat, None)
            wi = [r[0] for r in wr].index("JPN") + 1 if "JPN" in lat else None
            if wi:
                world = f"全世界では{len(wr)}か国・地域中{wi}位。"
        table = ""
        if m["rank"]:
            rows = ranking(m, lat, oecd)
            trs = "".join(
                f'<tr data-iso="{c}"{" class=jp" if c == "JPN" else ""}><td>{i + 1}</td><td>{esc(names.get(c, c))}</td>'
                f'<td class="num">{fmt_value(m, v)}</td><td class="num">{y}</td></tr>'
                for i, (c, y, v) in enumerate(rows))
            table = f"""<section class="block"><h2>OECD加盟国のランキング（{order_label(m)}）</h2>
<div class="table-wrap"><table class="rank"><thead><tr><th>順位</th><th>国</th><th class="num">値</th><th class="num">年</th></tr></thead>
<tbody>{trs}</tbody></table></div></section>"""
        rank_block = ""
        if m["rank"]:
            rank_block = f"""<section class="block">
  <div class="block-head"><h2>ランキング</h2>{group_tabs("oecd", REGION_JA[region_of["JPN"]])}</div>
  <p class="muted" id="rank-note">各国の最新の値（{RECENT_YEARS}年以内）で比べています。日本は赤で表示。</p>
  <div class="chart" id="chart-rank" role="img" aria-label="{esc(m['name'])}の国別ランキング"></div>
</section>"""
        rank_hist = ""
        if m["rank"]:
            rank_hist = f"""<section class="block">
  <div class="block-head"><h2 id="rh-title">日本の順位の推移</h2>{group_tabs("oecd", REGION_JA[region_of["JPN"]])}</div>
  <p class="muted">その年にデータがある国の中での順位です（{order_label(m)}）。</p>
  <div class="chart chart-sm" id="chart-rankhist" role="img" aria-label="順位の推移"></div>
  <p class="muted pad" id="rh-empty" hidden></p>
</section>"""
        if code.startswith("DERIVED."):
            src = ('世界銀行 World Development Indicators の購買力平価（<a href="https://data.worldbank.org/indicator/PA.NUS.PPP" '
                   'rel="noopener">PA.NUS.PPP</a>）を為替レート（<a href="https://data.worldbank.org/indicator/PA.NUS.FCRF" '
                   'rel="noopener">PA.NUS.FCRF</a>）で割って、このサイトで計算')
        else:
            src = (f'世界銀行 World Development Indicators（<a href="https://data.worldbank.org/indicator/{esc(code)}" '
                   f'rel="noopener">{esc(code)}</a>）')
        related = "".join(
            f'<li><a href="{S.href(depth, "i/" + M[c]["slug"] + "/")}">{esc(M[c]["name"])}</a></li>'
            for c in by_cat[m["cat"]] if c != code)
        related_block = f'<section class="block"><h2>{esc(m["cat"])}のほかの指標</h2><ul class="links">{related}</ul></section>' if related else ""
        cat_kw = next(k for n, s, k in CATEGORIES if n == m["cat"])
        report = ""
        if monetize.get("report_url"):
            report = f'<p class="muted"><a href="{esc(monetize["report_url"])}" rel="noopener" target="_blank">このページの誤りを報告する</a></p>'
        body = f"""
<nav class="crumbs"><a href="{S.href(depth, '')}">トップ</a> › <a href="{S.href(depth, 'd/' + CAT_SLUG[m['cat']] + '/')}">{esc(m['cat'])}</a></nav>
<h1>{esc(m['name'])}{'の国別ランキング' if m['rank'] else 'の推移'}</h1>
<div class="focus-pick"><label for="focus-sel">主役の国</label><select id="focus-sel"><option value="JPN">日本</option></select>
<a id="focus-link" href="{S.href(depth, '')}" hidden></a></div>
<p class="lead" id="lead">{lead}{(' ' + world) if world else ''}</p>
<p>{esc(m['desc'])}</p>
{rank_block}
<section class="block">
  <div class="block-head"><h2>推移</h2></div>
  <div class="chips" id="chips"></div>
  <div class="chart" id="chart-trend" role="img" aria-label="{esc(m['name'])}の推移"></div>
</section>
{rank_hist}
{table}
<p class="source">出典：{src}。CC BY 4.0。データ取得：{esc(manifest['fetched_at'][:10])}</p>
{report}
{related_block}
{S.books(cat_kw)}
"""
        S.write(f"i/{m['slug']}/", f"{m['name']}の国別ランキングと推移", f"{m['name']}の国別ランキングと日本の推移。"
                + lead.replace("<strong>", "").replace("</strong>", ""), body, depth, "indicator",
                f' data-slug="{m["slug"]}"',
                {"data/meta.json": meta, "data/latest.json": {m["slug"]: latest_json[m["slug"]]},
                 f"data/i/{m['slug']}.json": series_json[m["slug"]]})

    # ---- 分野ページ
    for name, slug, kw in CATEGORIES:
        codes = by_cat.get(name)
        if not codes:
            continue
        items = []
        for c in codes:
            m = M[c]
            s = jp_sentence(m, latest_all[c], oecd, "OECD加盟国") if m["rank"] else jp_sentence(m, latest_all[c], None, "")
            items.append(f'<li class="card"><a href="{S.href(2, "i/" + m["slug"] + "/")}"><span class="card-title">{esc(m["name"])}</span>'
                         f'<span class="card-text">{s}</span></a></li>')
        body = f"""<nav class="crumbs"><a href="{S.href(2, '')}">トップ</a> › <a href="{S.href(2, 'i/')}">指標一覧</a></nav>
<h1>{esc(name)}のデータで見る日本</h1>
<ul class="cards">{''.join(items)}</ul>
{S.books(kw)}"""
        S.write(f"d/{slug}/", f"{name}のデータで見る日本", f"{name}に関する指標で、日本と世界の国々を比べる。", body, 2, "category")

    # ---- 指標一覧
    secs = []
    for name, slug, kw in CATEGORIES:
        codes = by_cat.get(name)
        if not codes:
            continue
        lis = "".join(f'<li><a href="{S.href(1, "i/" + M[c]["slug"] + "/")}">{esc(M[c]["name"])}</a></li>' for c in codes)
        secs.append(f'<section class="block"><h2><a href="{S.href(1, "d/" + slug + "/")}">{esc(name)}</a></h2><ul class="links">{lis}</ul></section>')
    S.write("i/", "指標一覧", f"{len(active)}の指標で、日本と世界の国々を比べる。", "<h1>指標一覧</h1>" + "".join(secs), 1, "list")

    # ---- トップ：強み・弱み（OECD）を事前に書いておき、JS でまとまりを切り替える
    def sw_lists(members, focus="JPN"):
        strong, weak, feat = [], [], []
        for c in active:
            m = M[c]
            if not m["rank"] or focus not in latest_all[c]:
                continue
            rows = ranking(m, latest_all[c], members, focus)
            n = len(rows)
            size = len(set(members) | {focus}) if members else len(countries)
            if n < max(5, -(-size * 2 // 5)):  # まとまりの4割以上の国にデータがある指標だけ使う
                continue
            r = [x[0] for x in rows].index(focus) + 1
            item = (r / n, r, n, c, latest_all[c][focus])
            q = max(1, round(n * 0.25))
            if m["dir"] != 0:
                if r <= q:
                    strong.append(item)
                elif r > n - q:
                    weak.append(item)
            elif r <= 3 or r > n - 3:
                feat.append(item)
        strong.sort()
        weak.sort(reverse=True)
        feat.sort(key=lambda x: min(x[0], 1 - x[0]))
        return strong, weak, feat

    def cards(items, depth=0, focus="JPN"):
        out = []
        for _, r, n, c, (y, v) in items:
            m = M[c]
            anchor = "" if focus == "JPN" else "#" + focus
            out.append(f'<li class="card"><a href="{S.href(depth, "i/" + m["slug"] + "/")}{anchor}">'
                       f'<span class="card-rank">{r}<small>位 / {n}</small></span>'
                       f'<span class="card-title">{esc(m["name"])}</span>'
                       f'<span class="card-text">{fmt_value(m, v)}（{y}年・{order_label(m)}）</span></a></li>')
        return "".join(out) or '<li class="muted">該当なし</li>'

    def region_members(iso):
        return {k for k, v in region_of.items() if v == region_of[iso]}

    def sw_block(focus, depth, title):
        g = "oecd" if focus in oecd else "region"
        mem = oecd if g == "oecd" else region_members(focus)
        gname = GROUPS["oecd"][0] if g == "oecd" else REGION_JA[region_of[focus]]
        st, wk, ft = sw_lists(mem, focus)
        return g, f"""<section class="block">
  <div class="block-head"><h2>{esc(title)}</h2>{group_tabs(g, REGION_JA[region_of[focus]])}</div>
  <p class="muted" id="sw-note">比べる相手：<span id="sw-group">{esc(gname)}</span>。良し悪しがはっきりした指標で、上位4分の1に入るものを強み、下位4分の1のものを弱みとしています。</p>
  <div class="sw">
    <div><h3 class="sw-h strong">強み</h3><ul class="cards" id="sw-strong">{cards(st, depth, focus)}</ul></div>
    <div><h3 class="sw-h weak">弱み</h3><ul class="cards" id="sw-weak">{cards(wk, depth, focus)}</ul></div>
  </div>
  <h3 class="sw-h">良し悪しではなく、目立つところ</h3>
  <ul class="cards" id="sw-feat">{cards(ft, depth, focus)}</ul>
</section>"""

    def jump_select(label="ほかの国を主役にして見る", current="JPN"):
        return (f'<div class="focus-pick"><label for="country-jump">{esc(label)}</label>'
                f'<select id="country-jump"><option value="{current}">{esc(names.get(current, current))}</option></select></div>')

    pl = series.get("DERIVED.PRICE_LEVEL", {}).get("JPN", {})
    hero_note = ""
    if pl:
        y_hi = max(pl, key=lambda y: pl[y])
        y_last = max(pl)
        pr = ranking(dict(dir=-1), latest_values(series["DERIVED.PRICE_LEVEL"], maxy["DERIVED.PRICE_LEVEL"]), oecd)
        pj = [r[0] for r in pr].index("JPN") + 1 if "JPN" in [r[0] for r in pr] else None
        hero_note = (f"米国の物価を1とすると、日本の物価水準は{y_hi}年の{pl[y_hi]:.2f}から、{y_last}年には{pl[y_last]:.2f}になりました。"
                     + (f"OECD加盟国{len(pr)}か国の中で、低いほうから{pj}番目です。" if pj else ""))
    cat_links = "".join(
        f'<a class="pill" href="{S.href(0, "d/" + s + "/")}">{esc(n)}</a>' for n, s, _ in CATEGORIES if n in by_cat)
    g0, sw_html = sw_block("JPN", 0, "日本の強みと弱み")
    body = f"""
<section class="hero">
  <h1>日本は、世界の<br>どこにいるのか。</h1>
  <p class="lead">{len(active)}の指標で、日本と世界{len(countries)}の国・地域を比べます。ランキングと、1960年からの推移をグラフで。</p>
  <p class="pills">{cat_links}</p>
  {jump_select()}
</section>
{sw_html}
<section class="block">
  <div class="block-head"><h2>「安くなった日本」を数字で見る</h2></div>
  <p>{hero_note}</p>
  <div class="chart" id="chart-hero" role="img" aria-label="物価水準の推移（米国＝1）"></div>
  <p class="muted"><a href="{S.href(0, 'i/price-level/')}">物価水準のページへ</a></p>
</section>
"""
    S.write("", f"{SITE_NAME} ── {TAGLINE}", f"{len(active)}の指標で、日本と世界{len(countries)}の国・地域を比べるサイト。日本の強み・弱みと、1960年からの推移をグラフで。",
            body, 0, "home", f' data-focus="JPN" data-group="{g0}"',
            {"data/meta.json": meta, "data/latest.json": latest_json, "data/i/price-level.json": series_json.get("price-level")})

    # ---- 国のページ（日本はトップがその役）
    def country_href(depth, iso):
        return S.href(depth, "") if iso == "JPN" else S.href(depth, "c/" + iso.lower() + "/")

    for iso in country_pages:
        if iso == "JPN":
            continue
        nm = names.get(iso, iso)
        info = countries[iso]
        g, sw_html = sw_block(iso, 2, f"{nm}の強みと弱み")
        rows = []
        for c in active:
            m = M[c]
            mine, jp = latest_all[c].get(iso), latest_all[c].get("JPN")
            if not mine and not jp:
                continue
            wr = ""
            if m["rank"] and mine:
                rk = ranking(m, latest_all[c], None)
                wr = f"{[x[0] for x in rk].index(iso) + 1}位 / {len(rk)}"
            cell = lambda x: f"{fmt_value(m, x[1])}<small>（{x[0]}）</small>" if x else "—"
            rows.append(f'<tr><td><a href="{S.href(2, "i/" + m["slug"] + "/")}#{iso}">{esc(m["name"])}</a></td>'
                        f'<td class="num">{cell(mine)}</td><td class="num">{cell(jp)}</td><td class="num">{wr}</td></tr>')
        body = f"""<nav class="crumbs"><a href="{S.href(2, '')}">トップ</a> › <a href="{S.href(2, 'c/')}">国から見る</a></nav>
<h1>{esc(nm)}の強みと弱み</h1>
<p class="lead">{esc(nm)}（{esc(REGION_JA.get(region_of[iso], region_of[iso]))}・{esc(INCOME_JA.get(info['income_level'], info['income_level']))}）を、{len(active)}の指標で世界の国々と比べます。</p>
{jump_select("主役の国を変える", iso)}
{sw_html}
<section class="block">
  <h2>{esc(nm)}と日本を比べる</h2>
  <p class="muted">各指標の最新の値（かっこ内は年）。指標名から、{esc(nm)}を主役にしたランキングと推移のグラフへ進めます。</p>
  <div class="table-wrap"><table class="rank compare"><thead><tr><th>指標</th><th class="num">{esc(nm)}</th><th class="num">日本</th><th class="num">{esc(nm)}の世界順位</th></tr></thead>
  <tbody>{''.join(rows)}</tbody></table></div>
</section>
<p class="source">出典：世界銀行 World Development Indicators。CC BY 4.0。データ取得：{esc(manifest['fetched_at'][:10])}</p>
"""
        S.write(f"c/{iso.lower()}/", f"{nm}の強みと弱み ── データで見る{nm}と日本",
                f"{nm}を{len(active)}の指標で世界と比べ、強み・弱みと日本との違いをまとめたページ。", body, 2, "country",
                f' data-focus="{iso}" data-group="{g}"', {"data/meta.json": meta, "data/latest.json": latest_json})

    # ---- 国の一覧
    by_region = {}
    for iso in country_pages:
        by_region.setdefault(region_of[iso], []).append(iso)
    secs = []
    for rk, ja in REGION_JA.items():
        isos = sorted(by_region.get(rk, []), key=lambda k: names.get(k, k))
        if not isos:
            continue
        lis = "".join(f'<li><a href="{country_href(1, k)}">{esc(names.get(k, k))}</a></li>' for k in isos)
        secs.append(f'<section class="block"><h2>{esc(ja)}</h2><ul class="links">{lis}</ul></section>')
    S.write("c/", "国から見る", "世界の国・地域を主役にして、強み・弱みと日本との違いを見る。",
            "<h1>国から見る</h1><p>主役にしたい国を選ぶと、その国の強み・弱みと、日本との比較が見られます。</p>"
            + jump_select("国を選ぶ") + "".join(secs), 1, "countries", "", {"data/meta.json": meta})

    # ---- このサイトについて
    ad_lines = []
    if monetize.get("adsense_client"):
        ad_lines.append("このサイトは Google AdSense による広告を掲載しています。")
    if monetize.get("rakuten_affiliate_id"):
        ad_lines.append("このサイトは楽天アフィリエイトに参加しています。")
    if monetize.get("amazon_associate_tag"):
        ad_lines.append("Amazonのアソシエイトとして、このサイトは適格販売により収入を得ています。")
    ad_text = "".join(f"<p>{x}</p>" for x in ad_lines)
    support = ""
    if monetize.get("support_url"):
        support = f'<p>このサイトは個人で作っています。役に立ったら応援していただけると更新の励みになります。</p><p><a class="btn" href="{esc(monetize["support_url"])}" rel="noopener" target="_blank">応援する</a></p>'
    body = f"""<h1>このサイトについて</h1>
<p>{SITE_NAME}は、世界の国々のデータの中で日本がどの位置にいるのかを、ランキングと推移のグラフで見られるサイトです。</p>
<h2>データの出典</h2>
<p>世界銀行 World Development Indicators のデータを、世界銀行のAPIから毎月2回自動で取得しています（CC BY 4.0）。各ページの下に指標のコードと元データへのリンクを載せています。
「物価水準（米国＝1）」は、世界銀行の購買力平価を為替レートで割ってこのサイトで計算した値です。世界銀行はこのサイトを推薦・承認していません。</p>
<p>データ取得：{esc(manifest['fetched_at'][:10])}／収録：{len(active)}指標・{len(countries)}の国と地域</p>
<h2>ランキングの決め方</h2>
<p>指標ごとに、各国の最新の値（その指標の最新年から{RECENT_YEARS}年以内）を比べています。国によって最新年が違うため、表には年を併記しています。
「低いほど良い」とされる指標（失業率・乳児死亡率など）は低い順、それ以外は高い順に並べています。為替レートと購買力平価は、通貨ごとに単位が違うため順位をつけていません。</p>
<p>トップページの「強み・弱み」は、良し悪しがはっきりした指標だけを使い、比べる国のまとまりの中で上位4分の1を強み、下位4分の1を弱みとしています。どの指標を「良い」とするかはこのサイトの判断です。</p>
<h2>収録していない国・地域</h2>
<p>世界銀行の国別データに含まれない台湾などは収録していません。また、EUや「高所得国」のような地域のまとまりは除いています。</p>
<h2>広告について</h2>
<p>一部のページに広告（アフィリエイトリンクを含む）を掲載することがあります。広告にはPRと表示します。紹介料はデータの選び方や説明には影響しません。</p>
{ad_text}
<h2>プライバシー</h2>
<p>アクセスの集計に、個人を特定しない形のアクセス解析を使っています。広告を掲載する場合、広告配信事業者がCookieを使って興味に応じた広告を表示することがあります。</p>
<h2>免責</h2>
<p>データには誤りや改訂が含まれる可能性があります。このサイトの情報によって生じた損害について責任を負いかねます。投資などの判断は、元データや専門家の情報をご確認ください。</p>
{support}"""
    S.write("about/", "このサイトについて", f"{SITE_NAME}のデータの出典、ランキングの決め方、広告について。", body, 1, "about")

    # ---- 404, sitemap, robots
    S.write("404.html", "ページが見つかりません", "ページが見つかりません。",
            f'<h1>ページが見つかりません</h1><p><a href="/">トップへ</a></p>', None, "404")
    S.urls.remove(f"{S.site_url}/404.html")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(os.path.join(args.out, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for u in S.urls:
            f.write(f"  <url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>\n")
        f.write("</urlset>\n")
    with open(os.path.join(args.out, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {S.site_url}/sitemap.xml\n")

    print(f"built {len(S.urls)} pages, {len(active)} indicators -> {args.out}/")


if __name__ == "__main__":
    main()
