#!/usr/bin/env python3
"""Enrich an existing factor input JSON with Tencent quote prices."""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen


def to_tencent_symbol(symbol: str) -> str:
    code = str(symbol).split(".")[0]
    suffix = str(symbol).split(".")[-1].upper() if "." in str(symbol) else ""
    market = "sh" if suffix == "SH" or code.startswith(("6", "9")) else "sz"
    return f"{market}{code}"


def normalize_symbol(code: str, market: str) -> str:
    return f"{code}.{'SH' if market == 'sh' else 'SZ'}"


def parse_line(line: str) -> dict[str, Any] | None:
    match = re.match(r'v_(sh|sz)(\d{6})="(.*)";?', line.strip())
    if not match:
        return None
    market, code, body = match.groups()
    parts = body.split("~")
    if len(parts) < 38 or not parts[1]:
        return None
    try:
        price = float(parts[3])
        pre_close = float(parts[4])
        open_price = float(parts[5])
        amount_10k = float(parts[37])
        turnover = float(parts[38]) if len(parts) > 38 and parts[38] else None
        pe_ttm = float(parts[39]) if len(parts) > 39 and parts[39] else None
        market_cap_yi = float(parts[45]) if len(parts) > 45 and parts[45] else None
    except ValueError:
        return None
    if price <= 0:
        return None
    pct_change = (price / pre_close - 1) * 100 if pre_close > 0 else None
    return {
        "symbol": normalize_symbol(code, market),
        "name": parts[1],
        "current_price": price,
        "open": open_price,
        "pre_close": pre_close,
        "pct_change": pct_change,
        "amount": amount_10k * 10000,
        "turnover_rate": turnover,
        "pe_ttm": pe_ttm,
        "market_cap": market_cap_yi * 100000000 if market_cap_yi is not None else None,
        "source": "tencent.qt.gtimg.cn",
    }


def fetch_batch(symbols: list[str]) -> dict[str, dict[str, Any]]:
    url = "https://qt.gtimg.cn/q=" + ",".join(to_tencent_symbol(symbol) for symbol in symbols)
    with urlopen(url, timeout=20) as response:
        content = response.read().decode("gbk", errors="ignore")
    quotes = {}
    for line in content.splitlines():
        parsed = parse_line(line)
        if parsed:
            quotes[parsed["symbol"]] = parsed
    return quotes


def enrich(payload: dict[str, Any], batch_size: int) -> tuple[int, list[dict[str, Any]]]:
    stocks = [stock for stock in payload.get("stocks", []) if isinstance(stock, dict)]
    audits: list[dict[str, Any]] = []
    enriched = 0
    all_quotes: dict[str, dict[str, Any]] = {}
    symbols = [str(stock.get("symbol")) for stock in stocks if stock.get("symbol")]
    for idx in range(0, len(symbols), batch_size):
        batch = symbols[idx : idx + batch_size]
        try:
            all_quotes.update(fetch_batch(batch))
        except Exception as exc:  # pragma: no cover - network/source dependent
            audits.append({"batch": batch, "ok": False, "error": f"{type(exc).__name__}:{str(exc)[:240]}"})
        time.sleep(0.05)

    for stock in stocks:
        symbol = str(stock.get("symbol", ""))
        quote = all_quotes.get(symbol)
        if not quote:
            audits.append({"symbol": symbol, "ok": False, "error": "quote_not_found"})
            continue
        factors = stock.setdefault("factors", {})
        stock["name"] = stock.get("name") or quote.get("name")
        stock["current_price"] = quote["current_price"]
        stock["quote"] = quote
        factors["current_price"] = quote["current_price"]
        if quote.get("pe_ttm") is not None:
            factors["pe_ttm_snapshot"] = quote["pe_ttm"]
        enriched += 1
        audits.append({"symbol": symbol, "ok": True, "current_price": quote["current_price"]})

    universe = payload.setdefault("universe", {})
    universe["symbols"] = [stock.get("symbol") for stock in stocks if stock.get("symbol")]
    universe["stocks"] = [
        {
            "symbol": stock.get("symbol"),
            "name": stock.get("name", ""),
            "current_price": stock.get("current_price"),
        }
        for stock in stocks
    ]
    sources = list(payload.get("data_sources") or [])
    if "tencent.qt.gtimg.cn" not in sources:
        sources.append("tencent.qt.gtimg.cn")
    payload["data_sources"] = sources
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload["as_of"] = fetched_at[:10]
    payload["quote_enrichment"] = {
        "source": "tencent.qt.gtimg.cn",
        "fetched_at": fetched_at,
        "enriched": enriched,
        "audits": audits,
    }
    payload["market_view"] = (
        f"{payload.get('market_view', '')} 已使用腾讯实时行情补充候选股票当前价格；"
        f"成功覆盖 {enriched} 只股票。"
    ).strip()
    return enriched, audits


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: enrich_tencent_quote.py <input-factors.json> <output-factors.json>")
        return 2
    input_path = Path(argv[1])
    output_path = Path(argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    enriched, _ = enrich(payload, batch_size=80)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {output_path}")
    print(f"quote enriched: {enriched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
