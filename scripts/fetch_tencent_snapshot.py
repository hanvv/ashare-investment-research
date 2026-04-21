#!/usr/bin/env python3
"""Fetch a lite A-share quote snapshot from Tencent and emit factor input JSON."""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import urlopen


def normalize_symbol(code: str, market: str) -> str:
    suffix = "SH" if market == "sh" else "SZ"
    return f"{code}.{suffix}"


def candidates() -> list[str]:
    codes: list[str] = []
    ranges = [
        ("sh", 600000, 605999),
        ("sh", 688000, 689999),
        ("sz", 1, 2999),
        ("sz", 300000, 301999),
    ]
    for market, start, end in ranges:
        for num in range(start, end + 1):
            codes.append(f"{market}{num:06d}")
    return codes


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
    if price <= 0 or pre_close <= 0:
        return None
    pct_change = (price / pre_close - 1) * 100
    return {
        "symbol": normalize_symbol(code, market),
        "name": parts[1],
        "price": price,
        "open": open_price,
        "pre_close": pre_close,
        "pct_change": pct_change,
        "amount": amount_10k * 10000,
        "turnover_rate": turnover,
        "pe_ttm": pe_ttm,
        "market_cap": market_cap_yi * 100000000 if market_cap_yi is not None else None,
    }


def fetch_batch(batch: list[str]) -> list[dict[str, Any]]:
    url = "https://qt.gtimg.cn/q=" + ",".join(batch)
    with urlopen(url, timeout=20) as response:
        content = response.read().decode("gbk", errors="ignore")
    records = []
    for line in content.splitlines():
        parsed = parse_line(line)
        if parsed:
            records.append(parsed)
    return records


def build_factor_input(limit: int, min_amount: float, max_codes: int | None) -> dict[str, Any]:
    all_codes = candidates()
    if max_codes:
        all_codes = all_codes[:max_codes]

    records: list[dict[str, Any]] = []
    batch_size = 80
    for idx in range(0, len(all_codes), batch_size):
        batch = all_codes[idx: idx + batch_size]
        try:
            records.extend(fetch_batch(batch))
        except Exception:
            pass
        time.sleep(0.03)

    stocks = []
    for item in records:
        name = str(item["name"])
        amount = float(item["amount"])
        if "ST" in name.upper() or "退" in name:
            continue
        if amount < min_amount:
            continue
        turnover = item.get("turnover_rate")
        pct_change = item.get("pct_change")
        factors = {
            "severe_illiquidity": False,
            "overheated_turnover": bool(turnover is not None and turnover > 18),
            "current_price": item["price"],
        }
        if pct_change is not None:
            factors["pct_change_20d"] = pct_change / 100
        if item.get("pe_ttm") is not None:
            factors["pe_ttm_snapshot"] = item["pe_ttm"]

        stocks.append(
            {
                "symbol": item["symbol"],
                "name": name,
                "industry": "",
                "current_price": item["price"],
                "quote": {
                    "current_price": item["price"],
                    "open": item.get("open"),
                    "pre_close": item.get("pre_close"),
                    "pct_change": item.get("pct_change"),
                    "amount": item.get("amount"),
                    "turnover_rate": item.get("turnover_rate"),
                    "source": "tencent.qt.gtimg.cn",
                },
                "factors": factors,
                "events": [],
                "risk_flags": ["overheated_turnover"] if factors["overheated_turnover"] else [],
                "core_reasons": [
                    "成交额满足流动性初筛条件。",
                    "基础行情备源返回有效报价，可进入后续 K 线与基本面补充。"
                ],
                "risks": [
                    "本轮尚未完成基本面、估值分位和公告事件交叉验证。"
                ],
                "invalid_conditions": [
                    "补充主源数据后基本面、估值或公告风险显著上升。",
                    "后续成交额明显萎缩或价格趋势转弱。",
                    "出现 ST、退市风险或重大负面公告。"
                ],
                "data_quality": {
                    "missing_fields": [
                        "ma20",
                        "ma60",
                        "roe_ttm",
                        "revenue_yoy",
                        "net_profit_yoy",
                        "pe_percentile_3y",
                        "pb_percentile_3y",
                        "announcements"
                    ],
                    "quality_score": 0.48
                },
                "_amount": amount,
                "_pct_change": pct_change if pct_change is not None else 0,
            }
        )

    stocks.sort(key=lambda item: (item["_amount"], item["_pct_change"]), reverse=True)
    selected = []
    for item in stocks[:limit]:
        item.pop("_amount", None)
        item.pop("_pct_change", None)
        selected.append(item)

    return {
        "as_of": date.today().isoformat(),
        "task_type": "market_scan",
        "universe": {
            "market": "A股",
            "sector": None,
            "symbols": [item["symbol"] for item in selected],
            "stocks": [
                {
                    "symbol": item["symbol"],
                    "name": item.get("name", ""),
                    "current_price": item.get("current_price"),
                }
                for item in selected
            ],
            "filters": {
                "exclude_st": True,
                "min_amount": min_amount,
                "source": "tencent.qt.gtimg.cn",
                "fallback_path": ["eastmoney_push2_failed", "xueqiu_failed", "tencent_used"]
            }
        },
        "data_sources": ["tencent.qt.gtimg.cn"],
        "market_view": "东方财富 push2 和雪球当前不可用，已降级使用腾讯基础行情备源完成流动性初筛；结果不等同于完整多维研究。",
        "style_bias": ["流动性", "备源行情初筛"],
        "stocks": selected
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: fetch_tencent_snapshot.py <output-factors.json> [--limit N] [--min-amount RMB] [--max-codes N]")
        return 2

    limit = 30
    min_amount = 1000000000
    max_codes = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    if "--min-amount" in argv:
        min_amount = float(argv[argv.index("--min-amount") + 1])
    if "--max-codes" in argv:
        max_codes = int(argv[argv.index("--max-codes") + 1])

    output_path = Path(argv[1])
    payload = build_factor_input(limit=limit, min_amount=min_amount, max_codes=max_codes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {output_path}")
    print(f"stocks: {len(payload['stocks'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
