#!/usr/bin/env python3
"""Enrich factor input JSON with real fundamental and valuation percentile data.

Primary source:
- Fundamentals: AkShare financial analysis indicators.
- Valuation history: AkShare Baidu valuation series, using PE-TTM and PB over
  the recent three-year window to calculate stock-level percentiles.

The script never invents missing values. If a field cannot be fetched or parsed,
it remains in data_quality.missing_fields and is reported in the enrichment audit.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


FUNDAMENTAL_FIELDS = [
    "report_period",
    "roe_ttm",
    "revenue_yoy",
    "net_profit_yoy",
    "gross_margin",
    "net_margin",
    "ocf_to_net_profit",
    "debt_to_asset",
    "eps",
    "bps",
]

VALUATION_FIELDS = [
    "pe_ttm",
    "pb_lf",
    "pe_percentile_3y",
    "pb_percentile_3y",
]


def to_ak_symbol(symbol: str) -> str:
    return symbol.split(".")[0]


def parse_as_of(payload: dict[str, Any]) -> datetime:
    raw = str(payload.get("as_of") or datetime.now().strftime("%Y-%m-%d"))
    return datetime.strptime(raw[:10], "%Y-%m-%d")


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "false", "--"}:
        return None
    text = text.replace(",", "").replace("%", "")
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def ratio_from_percent(value: Any) -> float | None:
    number = safe_float(value)
    if number is None:
        return None
    return number / 100


def ratio_auto(value: Any) -> float | None:
    number = safe_float(value)
    if number is None:
        return None
    return number / 100 if abs(number) > 10 else number


def add_missing(data_quality: dict[str, Any], field: str) -> None:
    missing = list(data_quality.get("missing_fields") or [])
    if field not in missing:
        missing.append(field)
    data_quality["missing_fields"] = missing


def remove_missing(data_quality: dict[str, Any], fields: list[str]) -> None:
    missing = list(data_quality.get("missing_fields") or [])
    data_quality["missing_fields"] = [field for field in missing if field not in fields]


def latest_report_row(df: Any, as_of: datetime) -> dict[str, Any] | None:
    if df is None or len(df) == 0 or "日期" not in df:
        return None
    work = df.copy()
    work["__date"] = work["日期"].astype(str).str[:10]
    work["__dt"] = work["__date"].apply(lambda x: datetime.strptime(x, "%Y-%m-%d"))
    work = work[work["__dt"] <= as_of]
    if len(work) == 0:
        return None
    work = work.sort_values("__dt", ascending=False)
    return work.iloc[0].to_dict()


def fetch_fundamental(ak: Any, symbol: str, as_of: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    code = to_ak_symbol(symbol)
    audit = {"source": "akshare.stock_financial_analysis_indicator", "ok": False, "error": ""}
    try:
        start_year = str(max(1990, as_of.year - 4))
        df = ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year)
        row = latest_report_row(df, as_of)
        if not row:
            audit["error"] = "empty_or_no_report_before_as_of"
            return {}, audit

        factors: dict[str, Any] = {}
        mapping = {
            "report_period": ("日期", str),
            "roe_ttm": ("净资产收益率(%)", ratio_from_percent),
            "revenue_yoy": ("主营业务收入增长率(%)", ratio_from_percent),
            "net_profit_yoy": ("净利润增长率(%)", ratio_from_percent),
            "gross_margin": ("销售毛利率(%)", ratio_from_percent),
            "net_margin": ("销售净利率(%)", ratio_from_percent),
            "ocf_to_net_profit": ("经营现金净流量与净利润的比率(%)", ratio_auto),
            "debt_to_asset": ("资产负债率(%)", ratio_from_percent),
            "eps": ("加权每股收益(元)", safe_float),
            "bps": ("每股净资产_调整前(元)", safe_float),
        }
        for target, (source_col, parser) in mapping.items():
            if source_col not in row:
                continue
            value = parser(row.get(source_col))
            if value is not None and value != "":
                factors[target] = value

        audit.update({"ok": bool(factors), "report_period": factors.get("report_period"), "fields": sorted(factors)})
        return factors, audit
    except Exception as exc:  # pragma: no cover - network/source dependent
        audit["error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
        return {}, audit


def percentile_rank(values: list[float], current: float) -> float | None:
    clean = [value for value in values if isinstance(value, (int, float)) and value > 0]
    if not clean:
        return None
    less_or_equal = sum(1 for value in clean if value <= current)
    return round(less_or_equal / len(clean), 4)


def fetch_valuation_series(ak: Any, symbol: str, indicator: str, as_of: datetime) -> tuple[float | None, float | None, dict[str, Any]]:
    code = to_ak_symbol(symbol)
    audit = {"source": "akshare.stock_zh_valuation_baidu", "indicator": indicator, "ok": False, "error": ""}
    try:
        df = ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator, period="近三年")
        if df is None or len(df) == 0 or "date" not in df or "value" not in df:
            audit["error"] = "empty_series"
            return None, None, audit
        work = df.copy()
        work["__dt"] = work["date"].astype(str).str[:10].apply(lambda x: datetime.strptime(x, "%Y-%m-%d"))
        work["__value"] = work["value"].apply(safe_float)
        work = work[(work["__dt"] <= as_of) & (work["__value"] > 0)]
        if len(work) == 0:
            audit["error"] = "no_value_before_as_of"
            return None, None, audit
        work = work.sort_values("__dt")
        current = float(work.iloc[-1]["__value"])
        percentile = percentile_rank([float(v) for v in work["__value"].tolist()], current)
        audit.update(
            {
                "ok": current is not None and percentile is not None,
                "latest_date": str(work.iloc[-1]["date"])[:10],
                "rows": int(len(work)),
                "current": current,
                "percentile": percentile,
            }
        )
        return current, percentile, audit
    except Exception as exc:  # pragma: no cover - network/source dependent
        audit["error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
        return None, None, audit


def enrich_one(ak: Any, stock: dict[str, Any], as_of: datetime) -> dict[str, Any]:
    symbol = str(stock.get("symbol", ""))
    factors = stock.setdefault("factors", {})
    data_quality = stock.setdefault("data_quality", {"missing_fields": [], "quality_score": 0.5})
    audit: dict[str, Any] = {"symbol": symbol, "fundamental": {}, "valuation": {}}

    fundamental, fundamental_audit = fetch_fundamental(ak, symbol, as_of)
    audit["fundamental"] = fundamental_audit
    if fundamental:
        factors.update(fundamental)
        remove_missing(data_quality, [field for field in FUNDAMENTAL_FIELDS if field in fundamental])

    pe, pe_percentile, pe_audit = fetch_valuation_series(ak, symbol, "市盈率(TTM)", as_of)
    audit["valuation"]["pe_ttm"] = pe_audit
    if pe is not None:
        factors["pe_ttm"] = pe
        factors["pe_ttm_snapshot"] = pe
        remove_missing(data_quality, ["pe_ttm", "pe_ttm_snapshot"])
    if pe_percentile is not None:
        factors["pe_percentile_3y"] = pe_percentile
        remove_missing(data_quality, ["pe_percentile_3y"])

    pb, pb_percentile, pb_audit = fetch_valuation_series(ak, symbol, "市净率", as_of)
    audit["valuation"]["pb_lf"] = pb_audit
    if pb is not None:
        factors["pb_lf"] = pb
        remove_missing(data_quality, ["pb_lf"])
    if pb_percentile is not None:
        factors["pb_percentile_3y"] = pb_percentile
        remove_missing(data_quality, ["pb_percentile_3y"])

    for field in ["roe_ttm", "revenue_yoy", "net_profit_yoy", "pe_percentile_3y", "pb_percentile_3y"]:
        if field not in factors:
            add_missing(data_quality, field)

    current_quality = float(data_quality.get("quality_score", 0.5))
    got_fundamental = all(field in factors for field in ["roe_ttm", "revenue_yoy", "net_profit_yoy"])
    got_valuation = all(field in factors for field in ["pe_percentile_3y", "pb_percentile_3y"])
    if got_fundamental and got_valuation:
        data_quality["quality_score"] = max(current_quality, 0.78)
    elif got_fundamental or got_valuation:
        data_quality["quality_score"] = max(current_quality, 0.68)

    audit["filled_fields"] = sorted(set(fundamental) | {k for k in ["pe_ttm", "pb_lf", "pe_percentile_3y", "pb_percentile_3y"] if k in factors})
    audit["missing_fields_after"] = list(data_quality.get("missing_fields") or [])
    return audit


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: enrich_akshare_fundamental_valuation.py <input-factors.json> <output-factors.json>")
        return 2

    try:
        import akshare as ak
    except ImportError:
        print("AkShare is not installed or not importable")
        return 1

    input_path = Path(argv[1])
    output_path = Path(argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    as_of = parse_as_of(payload)

    audits = []
    enriched_fundamental = 0
    enriched_valuation = 0
    for stock in payload.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        audit = enrich_one(ak, stock, as_of)
        audits.append(audit)
        if audit.get("fundamental", {}).get("ok"):
            enriched_fundamental += 1
        valuation = audit.get("valuation", {})
        if valuation.get("pe_ttm", {}).get("ok") or valuation.get("pb_lf", {}).get("ok"):
            enriched_valuation += 1

    sources = list(payload.get("data_sources") or [])
    for source in ["akshare.stock_financial_analysis_indicator", "akshare.stock_zh_valuation_baidu"]:
        if source not in sources:
            sources.append(source)
    payload["data_sources"] = sources
    payload["market_view"] = (
        f"{payload.get('market_view', '')} 已尝试使用 AkShare 补充基本面字段和近三年估值分位；"
        f"基本面成功 {enriched_fundamental} 只，估值成功 {enriched_valuation} 只。"
    ).strip()
    payload["fundamental_valuation_enrichment"] = {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "fundamental_source": "akshare.stock_financial_analysis_indicator",
        "valuation_source": "akshare.stock_zh_valuation_baidu",
        "valuation_method": "latest positive PE-TTM/PB value percentile rank within the recent three-year series up to as_of",
        "enriched_fundamental": enriched_fundamental,
        "enriched_valuation": enriched_valuation,
        "audits": audits,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {output_path}")
    print(f"fundamental enriched: {enriched_fundamental}, valuation enriched: {enriched_valuation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
