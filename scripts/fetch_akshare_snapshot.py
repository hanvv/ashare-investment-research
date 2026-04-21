#!/usr/bin/env python3
"""Fetch an A-share market snapshot with AkShare and emit factor input JSON."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def pick(row: Any, names: list[str]) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def normalize_symbol(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return code


def build_factor_input(limit: int, min_amount: float) -> dict[str, Any]:
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("AkShare is not installed. Install with: py -m pip install akshare pandas") from exc

    spot = ak.stock_zh_a_spot_em()
    if spot is None or len(spot) == 0:
        raise RuntimeError("AkShare returned an empty A-share snapshot")

    records: list[dict[str, Any]] = []
    for _, row in spot.iterrows():
        row_dict = row.to_dict()
        code = pick(row_dict, ["代码", "code"])
        name = str(pick(row_dict, ["名称", "name"]) or "")
        amount = to_float(pick(row_dict, ["成交额", "amount"]))
        pct_change = to_float(pick(row_dict, ["涨跌幅", "pct_chg", "pct_change"]))
        turnover = to_float(pick(row_dict, ["换手率", "turnover"]))

        current_price = to_float(pick(row_dict, ["最新价", "price", "close"]))

        if not code or not name:
            continue
        if "ST" in name.upper() or "退" in name:
            continue
        if amount is None or amount < min_amount:
            continue

        factors = {
            "severe_illiquidity": False,
            "overheated_turnover": bool(turnover is not None and turnover > 18),
        }
        if current_price is not None:
            factors["current_price"] = current_price
        if pct_change is not None:
            factors["pct_change_20d"] = pct_change / 100

        records.append(
            {
                "symbol": normalize_symbol(str(code)),
                "name": name,
                "industry": "",
                "current_price": current_price,
                "quote": {
                    "current_price": current_price,
                    "pct_change": pct_change,
                    "amount": amount,
                    "turnover_rate": turnover,
                    "source": "akshare.stock_zh_a_spot_em",
                },
                "factors": factors,
                "events": [],
                "risk_flags": ["overheated_turnover"] if factors["overheated_turnover"] else [],
                "core_reasons": [
                    "成交额满足流动性过滤条件，具备进一步研究基础。"
                ],
                "risks": [
                    "当前初筛仅使用 AkShare 行情快照，缺少基本面、估值和公告事件验证。"
                ],
                "invalid_conditions": [
                    "补充基本面、估值或公告数据后显示风险显著上升。",
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
                    "quality_score": 0.45
                },
                "_amount": amount,
                "_pct_change": pct_change if pct_change is not None else 0,
            }
        )

    records.sort(key=lambda item: (item["_amount"], item["_pct_change"]), reverse=True)
    stocks = []
    for item in records[:limit]:
        item.pop("_amount", None)
        item.pop("_pct_change", None)
        stocks.append(item)

    return {
        "as_of": date.today().isoformat(),
        "task_type": "market_scan",
        "universe": {
            "market": "A股",
            "sector": None,
            "symbols": [item["symbol"] for item in stocks],
            "stocks": [
                {
                    "symbol": item["symbol"],
                    "name": item.get("name", ""),
                    "current_price": item.get("current_price"),
                }
                for item in stocks
            ],
            "filters": {
                "exclude_st": True,
                "min_amount": min_amount,
                "source": "akshare.stock_zh_a_spot_em"
            }
        },
        "data_sources": ["akshare.stock_zh_a_spot_em"],
        "market_view": "基于 AkShare A 股行情快照完成流动性初筛；因缺少基本面、估值和公告字段，结果仅用于候选池研究排序。",
        "style_bias": ["流动性", "行情初筛"],
        "stocks": stocks
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: fetch_akshare_snapshot.py <output-factors.json> [--limit N] [--min-amount RMB]")
        return 2

    limit = 30
    min_amount = 100000000
    if "--limit" in argv:
        idx = argv.index("--limit")
        if idx + 1 >= len(argv):
            print("--limit requires a value")
            return 2
        limit = int(argv[idx + 1])
    if "--min-amount" in argv:
        idx = argv.index("--min-amount")
        if idx + 1 >= len(argv):
            print("--min-amount requires a value")
            return 2
        min_amount = float(argv[idx + 1])

    output_path = Path(argv[1])
    payload = build_factor_input(limit=limit, min_amount=min_amount)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {output_path}")
    print(f"stocks: {len(payload['stocks'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
