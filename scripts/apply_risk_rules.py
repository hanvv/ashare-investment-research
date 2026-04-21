#!/usr/bin/env python3
"""Apply A-share research risk rules to a scored stock result."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


RATING_ORDER = ["回避", "中性", "观察", "关注", "强关注"]

ONE_VOTE_AVOID_FLAGS = {
    "is_st": "ST 或 *ST 标的默认回避。",
    "delisting_risk": "存在退市风险或退市整理风险。",
    "major_fraud_risk": "存在重大财务造假风险。",
    "capital_occupation": "存在控股股东资金占用风险。",
    "debt_default": "存在债务违约风险。",
    "going_concern_uncertainty": "存在持续经营重大不确定性。",
    "severe_illiquidity": "流动性严重不足，可能存在难以退出风险。",
    "severe_data_missing": "关键数据严重缺失，无法形成可靠判断。",
}

DOWNGRADE_FLAGS = {
    "shareholder_reduction": "存在大股东或高管减持风险。",
    "high_pledge": "股权质押比例较高。",
    "earnings_miss": "业绩预告或业绩表现低于预期。",
    "deducted_profit_deterioration": "扣非净利润明显恶化。",
    "ocf_profit_divergence": "经营现金流与利润存在明显背离。",
    "receivable_inventory_abnormal": "应收账款或存货增长异常。",
    "high_valuation_slow_growth": "估值处于高位且盈利增速放缓。",
    "overheated_turnover": "短期涨幅或换手过高，存在交易拥挤风险。",
    "regulatory_inquiry": "近期存在监管问询。",
    "major_litigation": "存在重大诉讼风险。",
    "penalty": "近期存在处罚或负面监管事项。",
}


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def rating_from_score(score: float) -> str:
    if score >= 85:
        return "强关注"
    if score >= 75:
        return "关注"
    if score >= 65:
        return "观察"
    if score >= 50:
        return "中性"
    return "回避"


def downgrade_rating(rating: str, steps: int) -> str:
    if rating not in RATING_ORDER:
        return rating
    idx = RATING_ORDER.index(rating)
    return RATING_ORDER[max(0, idx - steps)]


def collect_flags(stock: dict[str, Any]) -> set[str]:
    flags: set[str] = set()
    for source in (stock.get("risk_flags"), stock.get("event_flags")):
        if isinstance(source, list):
            flags.update(str(item) for item in source)

    factors = stock.get("factors", {})
    if isinstance(factors, dict):
        for key, value in factors.items():
            if value is True:
                flags.add(str(key))

    events = stock.get("events", [])
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            event_type = event.get("event_type")
            if event_type:
                flags.add(str(event_type))
            if event.get("impact") == "negative" and event.get("severity") == "high":
                flags.add("penalty")

    data_quality = stock.get("data_quality", {})
    if isinstance(data_quality, dict) and data_quality.get("quality_score", 1) < 0.4:
        flags.add("severe_data_missing")

    return flags


def apply_risk_rules(result: dict[str, Any], stock: dict[str, Any]) -> dict[str, Any]:
    flags = collect_flags(stock)
    risk_reasons: list[str] = []
    risk_flags = set(result.get("risk_flags") or [])

    avoid_reasons = [reason for flag, reason in ONE_VOTE_AVOID_FLAGS.items() if flag in flags]
    downgrade_reasons = [reason for flag, reason in DOWNGRADE_FLAGS.items() if flag in flags]

    for flag in flags:
        if flag in ONE_VOTE_AVOID_FLAGS or flag in DOWNGRADE_FLAGS:
            risk_flags.add(flag)

    score = float(result.get("total_score", 0))
    rating = str(result.get("rating", rating_from_score(score)))

    if avoid_reasons:
        score = min(score, 45)
        rating = "回避"
        risk_reasons.extend(avoid_reasons)
        result["risk_level"] = "extreme"
        result["avoid"] = True
        result["downgraded"] = True
    elif downgrade_reasons:
        penalty = min(30, 8 * len(downgrade_reasons))
        score = clamp(score - penalty)
        rating = downgrade_rating(rating_from_score(score), 1)
        risk_reasons.extend(downgrade_reasons)
        result["risk_level"] = "high" if len(downgrade_reasons) >= 2 else "medium"
        result["avoid"] = False
        result["downgraded"] = True
    else:
        result["risk_level"] = "low" if score >= 75 else "medium"
        result["avoid"] = False
        result["downgraded"] = False

    risks = list(result.get("risks") or [])
    for reason in risk_reasons:
        if reason not in risks:
            risks.append(reason)

    if risk_reasons:
        core_reasons = [
            reason
            for reason in list(result.get("core_reasons") or [])
            if "未识别到会直接覆盖评级的重大风险" not in str(reason)
        ]
        if not core_reasons:
            core_reasons = ["风险控制规则已触发，当前更适合作为风险复盘对象。"]
        result["core_reasons"] = core_reasons[:5]

    invalid_conditions = list(result.get("invalid_conditions") or [])
    default_invalid = [
        "出现重大负面公告、监管处罚或退市风险提示。",
        "关键趋势位跌破且成交额明显放大。",
        "下一期财务数据显著低于当前研究前提。",
    ]
    for condition in default_invalid:
        if condition not in invalid_conditions:
            invalid_conditions.append(condition)

    result["total_score"] = round(score, 2)
    result["rating"] = rating
    result["risk_flags"] = sorted(risk_flags)
    result["risks"] = risks[:5] if risks else ["未识别到重大单项风险，但仍需关注市场波动和数据更新。"]
    result["invalid_conditions"] = invalid_conditions[:5]
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("Usage: apply_risk_rules.py <result.json> <stock.json> <output.json>")
        return 2

    result_path = Path(argv[1])
    stock_path = Path(argv[2])
    output_path = Path(argv[3])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    stock = json.loads(stock_path.read_text(encoding="utf-8"))
    adjusted = apply_risk_rules(result, stock)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(adjusted, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
