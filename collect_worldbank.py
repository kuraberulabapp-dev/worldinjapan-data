#!/usr/bin/env python3
"""
World Bank 指標コレクター（WorldInJapan）

世界銀行 Open Data API (v2) から、INDICATORS に列挙した指標を全国分・全年分取得し、
data/ 以下に CSV として保存する。標準ライブラリのみで動作する。

出力:
  data/countries.csv              国コード・国名・地域・所得区分（集計地域は除外）
  data/indicators.csv             取得した指標の一覧（コード・名称・出典・単位）
  data/<INDICATOR_CODE>.csv       country_code,year,value  (値が無い年は出力しない)
  data/manifest.json              取得日時・件数・最終データ年

使い方:
  python3 collect_worldbank.py            # data/ に保存
  python3 collect_worldbank.py --out X    # 保存先を変更
  python3 collect_worldbank.py --only NY.GDP.PCAP.CD,SP.POP.TOTL   # 指標を絞る

ライセンス: World Bank Open Data は CC BY 4.0。表示例:
  "The World Bank: World Development Indicators: <指標名>"
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.worldbank.org/v2"

# 指標コード: (日本語名, カテゴリ)
INDICATORS = {
    "NY.GDP.MKTP.CD":      ("GDP（名目・米ドル）", "経済"),
    "NY.GDP.PCAP.CD":      ("一人当たりGDP（名目・米ドル）", "経済"),
    "NY.GDP.PCAP.PP.CD":   ("一人当たりGDP（購買力平価・国際ドル）", "経済"),
    "NY.GDP.MKTP.KD.ZG":   ("実質GDP成長率（%）", "経済"),
    "FP.CPI.TOTL.ZG":      ("消費者物価上昇率（%）", "経済"),
    "SL.UEM.TOTL.ZS":      ("失業率（%・ILO推計）", "労働"),
    "GC.DOD.TOTL.GD.ZS":   ("中央政府債務（対GDP比%）", "財政"),
    "NE.EXP.GNFS.ZS":      ("輸出（対GDP比%）", "貿易"),
    "SP.POP.TOTL":         ("総人口", "人口"),
    "SP.POP.GROW":         ("人口増加率（%）", "人口"),
    "SP.DYN.LE00.IN":      ("平均寿命（年）", "保健"),
    "SP.DYN.TFRT.IN":      ("合計特殊出生率", "人口"),
    "SP.POP.65UP.TO.ZS":   ("65歳以上人口比率（%）", "人口"),
    "SP.URB.TOTL.IN.ZS":   ("都市人口比率（%）", "人口"),
    "SH.XPD.CHEX.GD.ZS":   ("医療支出（対GDP比%）", "保健"),
    "SE.XPD.TOTL.GD.ZS":   ("教育支出（対GDP比%）", "教育"),
    "IT.NET.USER.ZS":      ("インターネット利用率（%）", "技術"),
    "EN.GHG.CO2.PC.CE.AR5": ("一人当たりCO2排出量（t）", "環境"),
    "EG.FEC.RNEW.ZS":      ("再生可能エネルギー比率（最終消費・%）", "環境"),
    "SI.POV.GINI":         ("ジニ係数", "格差"),
    "MS.MIL.XPND.GD.ZS":   ("軍事支出（対GDP比%）", "安全保障"),
    "AG.LND.FRST.ZS":      ("森林面積比率（%）", "環境"),
    # --- 第1段階の追加（2026-10-22）: 日本の強み・弱み／経済ニュースの裏付け ---
    "GB.XPD.RSDV.GD.ZS":   ("研究開発費（対GDP比%）", "技術"),
    "SP.POP.SCIE.RD.P6":   ("研究者数（人口100万人あたり）", "技術"),
    "IP.PAT.RESD":         ("特許出願数（居住者）", "技術"),
    "TX.VAL.TECH.MF.ZS":   ("ハイテク製品輸出比率（工業製品輸出に占める%）", "技術"),
    "NV.IND.MANF.ZS":      ("製造業付加価値（対GDP比%）", "経済"),
    "VC.IHR.PSRC.P5":      ("殺人発生率（人口10万人あたり）", "安全"),
    "SP.DYN.IMRT.IN":      ("乳児死亡率（出生1000人あたり）", "保健"),
    "SH.MED.PHYS.ZS":      ("医師数（人口1000人あたり）", "保健"),
    "SE.TER.ENRR":         ("高等教育就学率（%）", "教育"),
    "EG.IMP.CONS.ZS":      ("エネルギー輸入依存度（純輸入・消費比%）", "エネルギー"),
    "EG.USE.PCAP.KG.OE":   ("一人当たりエネルギー消費（石油換算kg）", "エネルギー"),
    "SL.TLF.CACT.FE.ZS":   ("女性の労働参加率（15歳以上・%）", "ジェンダー"),
    "SG.GEN.PARL.ZS":      ("女性国会議員比率（%）", "ジェンダー"),
    "BN.CAB.XOKA.GD.ZS":   ("経常収支（対GDP比%）", "国際収支"),
    "BX.KLT.DINV.WD.GD.ZS": ("対内直接投資（純流入・対GDP比%）", "国際収支"),
    "FI.RES.TOTL.CD":      ("外貨準備（金を含む・米ドル）", "国際収支"),
    "PA.NUS.FCRF":         ("対ドル為替レート（年平均・自国通貨/ドル）", "為替"),
    "PA.NUS.PPP":          ("購買力平価（GDP・自国通貨/国際ドル）", "為替"),
    "ST.INT.ARVL":         ("入国観光客数", "観光"),
    "ST.INT.RCPT.CD":      ("観光収入（米ドル）", "観光"),
    "GC.TAX.TOTL.GD.ZS":   ("税収（対GDP比%）", "財政"),
}

UA = "WorldInJapan-collector/0.1 (+https://github.com/)"


def fetch_json(url, retries=4, backoff=3.0):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
            last = e
            time.sleep(backoff * (i + 1))
    raise RuntimeError(f"fetch failed after {retries} tries: {url}: {last}")


def paged(path, **params):
    """World Bank API のページングを吸収して全レコードを返す。"""
    params.setdefault("format", "json")
    params.setdefault("per_page", 20000)
    page = 1
    out = []
    while True:
        params["page"] = page
        url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
        data = fetch_json(url)
        if not isinstance(data, list) or len(data) < 2:
            # エラー応答は [{"message": [...]}] の形
            msg = data[0] if isinstance(data, list) and data else data
            raise RuntimeError(f"unexpected response for {url}: {str(msg)[:200]}")
        meta, rows = data[0], data[1] or []
        out.extend(rows)
        if page >= int(meta.get("pages", 1)):
            break
        page += 1
    return out


def get_countries():
    rows = paged("country")
    countries = []
    for c in rows:
        region = (c.get("region") or {}).get("id", "")
        if region in ("", "NA"):  # 集計地域（World, EU 等）を除外
            continue
        countries.append({
            "country_code": c["id"],
            "iso2": c.get("iso2Code", ""),
            "name_en": c.get("name", ""),
            "region": (c.get("region") or {}).get("value", ""),
            "income_level": (c.get("incomeLevel") or {}).get("value", ""),
            "capital": c.get("capitalCity", ""),
        })
    countries.sort(key=lambda x: x["country_code"])
    return countries


def get_indicator_meta(code):
    data = fetch_json(f"{BASE}/indicator/{code}?format=json")
    if isinstance(data, list) and len(data) >= 2 and data[1]:
        m = data[1][0]
        return {
            "name_en": m.get("name", ""),
            "unit": m.get("unit", ""),
            "source": (m.get("source") or {}).get("value", ""),
            "source_org": m.get("sourceOrganization", ""),
            "note": m.get("sourceNote", ""),
        }
    return {"name_en": "", "unit": "", "source": "", "source_org": "", "note": ""}


def get_indicator_values(code, valid_codes):
    rows = paged(f"country/all/indicator/{code}")
    out = []
    for r in rows:
        v = r.get("value")
        cc = r.get("countryiso3code") or (r.get("country") or {}).get("id")
        if v is None or cc not in valid_codes:
            continue
        out.append((cc, int(r["date"]), v))
    out.sort()
    return out


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--only", default="", help="カンマ区切りの指標コード")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    codes = [c.strip() for c in args.only.split(",") if c.strip()] or list(INDICATORS)

    print("countries ...", flush=True)
    countries = get_countries()
    valid = {c["country_code"] for c in countries}
    write_csv(os.path.join(args.out, "countries.csv"),
              ["country_code", "iso2", "name_en", "region", "income_level", "capital"],
              [[c[k] for k in ("country_code", "iso2", "name_en", "region", "income_level", "capital")] for c in countries])
    print(f"  {len(countries)} countries", flush=True)

    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "World Bank Open Data API v2 (CC BY 4.0)",
        "countries": len(countries),
        "indicators": {},
    }
    ind_rows = []
    failed = []
    for code in codes:
        ja, cat = INDICATORS.get(code, (code, ""))
        print(f"{code} ...", flush=True)
        try:
            meta = get_indicator_meta(code)
            vals = get_indicator_values(code, valid)
        except Exception as e:  # 1指標の失敗で全体を止めない
            print(f"  FAILED: {e}", file=sys.stderr, flush=True)
            failed.append({"code": code, "error": str(e)[:300]})
            continue
        write_csv(os.path.join(args.out, f"{code}.csv"), ["country_code", "year", "value"], vals)
        years = [y for _, y, _ in vals]
        latest = max(years) if years else None
        latest_count = sum(1 for y in years if y == latest) if latest else 0
        manifest["indicators"][code] = {
            "name_ja": ja, "category": cat, "rows": len(vals),
            "min_year": min(years) if years else None,
            "max_year": latest, "countries_at_max_year": latest_count,
        }
        ind_rows.append([code, ja, cat, meta["name_en"], meta["unit"], meta["source"], meta["source_org"],
                         len(vals), min(years) if years else "", latest or ""])
        print(f"  {len(vals)} rows, {min(years) if years else '-'}–{latest}", flush=True)
        time.sleep(0.5)  # 礼儀としての間隔

    write_csv(os.path.join(args.out, "indicators.csv"),
              ["code", "name_ja", "category", "name_en", "unit", "source", "source_org", "rows", "min_year", "max_year"],
              ind_rows)
    manifest["failed"] = failed
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"done: {len(ind_rows)} indicators ok, {len(failed)} failed -> {args.out}/", flush=True)
    return 1 if (failed and not ind_rows) else 0


if __name__ == "__main__":
    sys.exit(main())
