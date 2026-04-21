#!/usr/bin/env python3
"""Enrich factor input JSON with A-share daily K-line trend factors.

This script follows the AkShare call pattern used by
D:/Desktop/a-stock-monitor-1.1.2/a-stock-quant/data/fetchers/history_fetcher.py:
ak.stock_zh_a_hist(symbol=code, period="daily", start_date=YYYYMMDD,
end_date=YYYYMMDD, adjust="qfq"). It intentionally does not read that
project's SQLite cache.

When AkShare's Eastmoney history endpoint is unavailable, it follows the
UZI-Skill A-share K-line fallback idea: AkShare EM -> AkShare Sina -> direct
Sina HTTP -> direct Tencent ifzq HTTP. No local sqlite cache is used.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


def to_ak_symbol(symbol: str) -> str:
    return symbol.split(".")[0]


def normalize_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    if "-" in date_str:
        return date_str.replace("-", "")
    return date_str


def market_suffix(code: str) -> str:
    return "SH" if code.startswith("6") else "SZ"


def fetch_akshare_hist(
    ak: Any, symbol: str, start_date: str, end_date: str
) -> list[dict[str, Any]]:
    code = to_ak_symbol(symbol)
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",
    )
    if df is None or len(df) == 0:
        return []

    rename_map = {
        "日期": "trade_date",
        "股票代码": "ts_code",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
        "振幅": "amplitude",
        "涨跌幅": "pct_chg",
        "涨跌额": "change",
        "换手率": "turnover",
    }
    df = df.rename(columns=rename_map)
    if "trade_date" not in df or "close" not in df or "amount" not in df:
        return []

    df["ts_code"] = f"{code}.{market_suffix(code)}"
    df["trade_date"] = df["trade_date"].astype(str).str[:10]
    today = datetime.now().strftime("%Y-%m-%d")
    df = df[df["trade_date"] <= today]

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "pct_chg",
        "turnover",
    ]:
        if column in df:
            df[column] = df[column].apply(
                lambda value: float(value) if value not in ("", None) else None
            )

    columns = [
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "pct_chg",
        "turnover",
    ]
    return df[[column for column in columns if column in df]].to_dict("records")


def fetch_akshare_sina(
    ak: Any, symbol: str, start_date: str, adjust: str
) -> list[dict[str, Any]]:
    code = to_ak_symbol(symbol)
    sina_symbol = ("sh" if symbol.endswith(".SH") else "sz") + code
    df = ak.stock_zh_a_daily(
        symbol=sina_symbol,
        start_date=start_date,
        adjust="qfq" if adjust == "qfq" else "",
    )
    if df is None or len(df) == 0:
        return []
    rename_map = {
        "date": "trade_date",
        "open": "open",
        "close": "close",
        "high": "high",
        "low": "low",
        "volume": "volume",
        "amount": "amount",
    }
    df = df.rename(columns=rename_map)
    if "trade_date" not in df or "close" not in df:
        return []
    df["ts_code"] = f"{code}.{market_suffix(code)}"
    df["trade_date"] = df["trade_date"].astype(str).str[:10]
    today = datetime.now().strftime("%Y-%m-%d")
    df = df[df["trade_date"] <= today]
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        if column in df:
            df[column] = df[column].apply(
                lambda value: float(value) if value not in ("", None) else None
            )
    columns = [
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]
    return df[[column for column in columns if column in df]].to_dict("records")


def fetch_sina_direct(symbol: str, limit: int) -> list[dict[str, Any]]:
    if requests is None:
        return []
    code = to_ak_symbol(symbol)
    sina_symbol = ("sh" if symbol.endswith(".SH") else "sz") + code
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {"symbol": sina_symbol, "scale": "240", "ma": "no", "datalen": str(limit)}
    response = requests.get(
        url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"}
    )
    data = response.json() if response.text and response.text != "null" else []
    rows = []
    for item in data:
        rows.append(
            {
                "ts_code": f"{code}.{market_suffix(code)}",
                "trade_date": str(item.get("day", ""))[:10],
                "open": float(item.get("open", 0) or 0),
                "high": float(item.get("high", 0) or 0),
                "low": float(item.get("low", 0) or 0),
                "close": float(item.get("close", 0) or 0),
                "volume": float(item.get("volume", 0) or 0),
            }
        )
    return [row for row in rows if row["trade_date"] and row["close"] > 0]


def fetch_tencent_ifzq(symbol: str, limit: int, adjust: str) -> list[dict[str, Any]]:
    if requests is None:
        return []
    code = to_ak_symbol(symbol)
    tx_symbol = ("sh" if symbol.endswith(".SH") else "sz") + code
    fq = "qfq" if adjust == "qfq" else ""
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"param": f"{tx_symbol},day,,,{limit},{fq}"}
    response = requests.get(
        url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"}
    )
    payload = response.json().get("data", {}).get(tx_symbol, {})
    klines = payload.get("qfqday") or payload.get("day") or []
    rows = []
    for line in klines:
        if len(line) >= 6:
            rows.append(
                {
                    "ts_code": f"{code}.{market_suffix(code)}",
                    "trade_date": str(line[0])[:10],
                    "open": float(line[1]),
                    "close": float(line[2]),
                    "high": float(line[3]),
                    "low": float(line[4]),
                    "volume": float(line[5]),
                }
            )
    return rows


def remove_missing(data_quality: dict[str, Any], fields: list[str]) -> None:
    missing = list(data_quality.get("missing_fields") or [])
    data_quality["missing_fields"] = [field for field in missing if field not in fields]


def add_missing(data_quality: dict[str, Any], field: str) -> None:
    missing = list(data_quality.get("missing_fields") or [])
    if field not in missing:
        missing.append(field)
    data_quality["missing_fields"] = missing


def fetch_kline_chain(
    ak: Any, symbol: str, start_date: str, end_date: str, days: int, adjust: str
) -> tuple[list[dict[str, Any]], str, list[str]]:
    errors: list[str] = []
    limit = max(days, 120)

    try:
        rows = fetch_akshare_hist(ak, symbol, start_date, end_date)
        if rows:
            return rows, "akshare.stock_zh_a_hist", errors
    except Exception as exc:
        errors.append(f"akshare-em:{type(exc).__name__}:{str(exc)[:120]}")

    try:
        rows = fetch_akshare_sina(ak, symbol, start_date, adjust)
        if rows:
            return rows, "akshare.stock_zh_a_daily", errors
    except Exception as exc:
        errors.append(f"akshare-sina:{type(exc).__name__}:{str(exc)[:120]}")

    try:
        rows = fetch_sina_direct(symbol, limit)
        if rows:
            return rows, "sina.direct.kline", errors
    except Exception as exc:
        errors.append(f"sina-direct:{type(exc).__name__}:{str(exc)[:120]}")

    try:
        rows = fetch_tencent_ifzq(symbol, limit, adjust)
        if rows:
            return rows, "tencent.ifzq.kline", errors
    except Exception as exc:
        errors.append(f"tencent-ifzq:{type(exc).__name__}:{str(exc)[:120]}")

    return [], "", errors


def enrich_one(
    ak: Any,
    stock: dict[str, Any],
    start_date: str,
    end_date: str,
    days: int,
    adjust: str,
) -> tuple[bool, str, list[str]]:
    symbol = str(stock.get("symbol", ""))
    if not symbol:
        return False, "", ["missing-symbol"]

    rows, source, errors = fetch_kline_chain(
        ak, symbol, start_date, end_date, days, adjust
    )
    if len(rows) < max(70, days):
        return False, source, errors or [f"insufficient rows: {len(rows)}"]

    rows = rows[-max(days, 80) :]
    closes = [float(row["close"]) for row in rows if row.get("close") is not None]
    amounts = [float(row["amount"]) for row in rows if row.get("amount") is not None]
    highs = [
        float(row.get("high", row["close"]))
        for row in rows
        if row.get("close") is not None
    ]
    if len(closes) < 60:
        return False

    close = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    prev_ma20 = sum(closes[-21:-1]) / 20
    ma60 = sum(closes[-60:]) / 60
    prev_ma60 = sum(closes[-61:-1]) / 60 if len(closes) >= 61 else ma60
    amount_ma20 = sum(amounts[-20:]) / 20
    high_20d_prev = max(highs[-21:-1]) if len(highs) >= 21 else max(highs[-20:])
    pct_change_20d = (
        close / closes[-21] - 1 if len(closes) >= 21 and closes[-21] else None
    )

    factors = stock.setdefault("factors", {})
    factors.update(
        {
            "close_above_ma20": close > ma20,
            "ma20_up": ma20 > prev_ma20,
            "close_above_ma60": close > ma60,
            "ma60_up": ma60 > prev_ma60,
            "ma20_above_ma60": ma20 > ma60,
            "breakout_20d": close >= high_20d_prev,
            "amount_ma20": amount_ma20,
        }
    )
    if pct_change_20d is not None:
        factors["pct_change_20d"] = pct_change_20d

    reasons = list(stock.get("core_reasons") or [])
    if close > ma20 and ma20 > prev_ma20:
        reasons.append("20 日均线趋势改善，价格位于短期均线上方。")
    if close > ma60 and ma20 > ma60:
        reasons.append("价格位于 60 日均线上方，短中期结构相对更稳。")
    if close >= high_20d_prev:
        reasons.append("价格接近或突破近 20 日高点。")
    stock["core_reasons"] = list(dict.fromkeys(reasons))[:3]

    risks = list(stock.get("risks") or [])
    if close < ma60:
        risks.append("价格仍低于 60 日均线，中期趋势确认不足。")
    if pct_change_20d is not None and pct_change_20d > 0.35:
        risks.append("近 20 日涨幅较高，需警惕短期交易拥挤。")
    stock["risks"] = list(dict.fromkeys(risks))[:3]

    data_quality = stock.setdefault(
        "data_quality", {"missing_fields": [], "quality_score": 0.48}
    )
    remove_missing(data_quality, ["ma20", "ma60", "akshare_kline"])
    current_quality = float(data_quality.get("quality_score", 0.48))
    data_quality["quality_score"] = max(current_quality, 0.58)
    stock["kline_source"] = {
        "source": source,
        "adjust": adjust,
        "start_date": rows[0]["trade_date"],
        "end_date": rows[-1]["trade_date"],
        "rows": len(rows),
        "uses_sqlite_cache": False,
    }
    return True, source, errors


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "Usage: enrich_akshare_kline.py <input-factors.json> <output-factors.json> [--days N] [--start-date YYYYMMDD] [--end-date YYYYMMDD] [--adjust qfq]"
        )
        return 2

    days = 120
    adjust = "qfq"
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=max(220, days * 2))).strftime(
        "%Y%m%d"
    )
    if "--start-date" in argv:
        start_date = normalize_date(argv[argv.index("--start-date") + 1])
    if "--end-date" in argv:
        end_date = normalize_date(argv[argv.index("--end-date") + 1])
    if "--adjust" in argv:
        adjust = argv[argv.index("--adjust") + 1]

    try:
        import akshare as ak
    except ImportError:
        print("AkShare is not installed")
        return 1

    input_path = Path(argv[1])
    output_path = Path(argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    enriched = 0
    failed = 0
    failure_reasons: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for stock in payload.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        try:
            ok, source, errors = enrich_one(
                ak, stock, start_date, end_date, days, adjust
            )
            if ok:
                enriched += 1
                source_counts[source] = source_counts.get(source, 0) + 1
            else:
                failed += 1
                reason = (
                    "; ".join(errors[:2]) if errors else "empty_or_insufficient_kline"
                )
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                add_missing(stock.setdefault("data_quality", {}), "akshare_kline")
        except Exception as exc:
            failed += 1
            reason = type(exc).__name__
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
            stock["kline_error"] = {
                "source": "akshare.stock_zh_a_hist",
                "error_type": reason,
                "message": str(exc)[:300],
                "uses_sqlite_cache": False,
            }
            add_missing(stock.setdefault("data_quality", {}), "akshare_kline")

    sources = list(payload.get("data_sources") or [])
    for source in [
        "akshare.stock_zh_a_hist",
        "akshare.stock_zh_a_daily",
        "sina.direct.kline",
        "tencent.ifzq.kline",
    ]:
        if source_counts.get(source) and source not in sources:
            sources.append(source)
    payload["data_sources"] = sources
    payload["market_view"] = (
        f"{payload.get('market_view', '')} 已尝试使用 AkShare 补充 K 线趋势因子，"
        f"调用方式参考 a-stock-quant 与 UZI-Skill 的 K 线 fallback 链；"
        f"成功 {enriched} 只，失败 {failed} 只。"
    ).strip()
    payload["kline_enrichment"] = {
        "source_chain": [
            "akshare.stock_zh_a_hist",
            "akshare.stock_zh_a_daily",
            "sina.direct.kline",
            "tencent.ifzq.kline",
        ],
        "source_counts": source_counts,
        "adjust": adjust,
        "start_date": start_date,
        "end_date": end_date,
        "uses_sqlite_cache": False,
        "enriched": enriched,
        "failed": failed,
        "failure_reasons": failure_reasons,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"WROTE {output_path}")
    print(f"enriched: {enriched}, failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
