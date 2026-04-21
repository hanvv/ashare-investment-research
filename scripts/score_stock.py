#!/usr/bin/env python3
"""Score A-share stocks from real factor data."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from apply_risk_rules import apply_risk_rules, rating_from_score


METHODOLOGY_VERSION = "ashare-research-signal-v1.2"
DISCLAIMER = (
    "本结果基于公开数据和规则化评分模型生成，仅用于投资研究辅助；"
    "不构成收益承诺、买卖建议或个性化投顾服务。"
)


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def bool_score(factors: dict[str, Any], key: str, points: float) -> float:
    return points if factors.get(key) is True else 0


def number(factors: dict[str, Any], key: str, default: float | None = None) -> float | None:
    value = factors.get(key, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def score_trend(factors: dict[str, Any]) -> float:
    score = 50
    score += bool_score(factors, "close_above_ma20", 10)
    score += bool_score(factors, "ma20_up", 8)
    score += bool_score(factors, "close_above_ma60", 10)
    score += bool_score(factors, "ma60_up", 8)
    score += bool_score(factors, "ma20_above_ma60", 8)
    score += bool_score(factors, "breakout_20d", 8)
    relative_strength = number(factors, "relative_strength_20d")
    if relative_strength is not None:
        score += 10 if relative_strength >= 0.7 else -8 if relative_strength < 0.3 else 0
    pct_change_20d = number(factors, "pct_change_20d")
    if pct_change_20d is not None and pct_change_20d > 0.35:
        score -= 15
    score -= bool_score(factors, "high_volume_stalling", 10)
    score -= bool_score(factors, "breakdown_ma60_with_volume", 15)
    return clamp(score)


def score_fundamental(factors: dict[str, Any]) -> float:
    score = 50
    roe = number(factors, "roe_ttm")
    if roe is not None:
        score += 10 if roe > 0.12 else -10 if roe < 0.04 else 0
    revenue_yoy = number(factors, "revenue_yoy")
    if revenue_yoy is not None:
        score += 8 if revenue_yoy > 0 else -8
    net_profit_yoy = number(factors, "net_profit_yoy")
    if net_profit_yoy is not None:
        score += 8 if net_profit_yoy > 0 else -10
    ocf_to_net_profit = number(factors, "ocf_to_net_profit")
    if ocf_to_net_profit is not None:
        score += 10 if ocf_to_net_profit > 0.8 else -12 if ocf_to_net_profit < 0.3 else 0
    score += bool_score(factors, "gross_margin_stable_or_up", 6)
    score -= bool_score(factors, "high_debt_vs_industry", 10)
    score -= bool_score(factors, "receivable_inventory_abnormal", 10)
    score -= bool_score(factors, "deducted_profit_deterioration", 15)
    return clamp(score)


def score_valuation(factors: dict[str, Any]) -> float:
    score = 50
    pe_pct = number(factors, "pe_percentile_3y")
    pb_pct = number(factors, "pb_percentile_3y")
    peg = number(factors, "peg")
    if pe_pct is not None:
        score += 10 if 0.2 <= pe_pct <= 0.6 else -15 if pe_pct >= 0.9 else 0
    if pb_pct is not None:
        score += 8 if 0.2 <= pb_pct <= 0.6 else -12 if pb_pct >= 0.9 else 0
    if peg is not None:
        score += 8 if 0.5 <= peg <= 1.5 else -8 if peg > 2 else 0
    score += bool_score(factors, "valuation_below_industry_with_quality", 8)
    score -= bool_score(factors, "high_valuation_slow_growth", 20)
    score -= bool_score(factors, "cyclical_low_pe_trap", 15)
    return clamp(score)


def score_event(factors: dict[str, Any], events: list[Any]) -> float:
    score = 60
    score += bool_score(factors, "positive_earnings_guidance", 15)
    score += bool_score(factors, "large_repurchase_cancel", 12)
    score += bool_score(factors, "insider_increase", 8)
    score += bool_score(factors, "major_contract", 8)
    score -= bool_score(factors, "shareholder_reduction", 15)
    score -= bool_score(factors, "regulatory_inquiry", 10)
    score -= bool_score(factors, "penalty", 20)
    score -= bool_score(factors, "negative_earnings_guidance", 20)
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("impact") == "positive":
            score += 8 if event.get("severity") == "high" else 4
        elif event.get("impact") == "negative":
            score -= 12 if event.get("severity") == "high" else 6
    return clamp(score)


def score_risk(factors: dict[str, Any], data_quality: dict[str, Any]) -> float:
    score = 85
    for key in [
        "is_st",
        "delisting_risk",
        "major_fraud_risk",
        "capital_occupation",
        "debt_default",
        "going_concern_uncertainty",
        "severe_illiquidity",
        "high_pledge",
        "overheated_turnover",
        "major_litigation",
    ]:
        if factors.get(key) is True:
            score -= 20 if key in {"is_st", "delisting_risk", "major_fraud_risk"} else 10
    quality = data_quality.get("quality_score", 1) if isinstance(data_quality, dict) else 1
    if isinstance(quality, (int, float)):
        score -= (1 - quality) * 25
    return clamp(score)


def weighted_score(dimensions: dict[str, float], weights: dict[str, float] | None = None) -> float:
    weights = weights or {
        "trend_volume_price": 0.30,
        "fundamental_quality": 0.25,
        "valuation": 0.15,
        "event": 0.15,
        "risk": 0.15,
    }
    return round(sum(dimensions[key] * weights[key] for key in weights), 2)


def default_position_range(rating: str) -> dict[str, Any]:
    ranges = {
        "寮哄叧娉?": (0, 0.10),
        "鍏虫敞": (0, 0.08),
        "瑙傚療": (0, 0.05),
        "涓€?": (0, 0.03),
        "鍥為伩": (0, 0),
    }
    low, high = ranges.get(rating, (0, 0.03))
    return {"min": low, "max": high, "unit": "portfolio_weight"}


def fmt_bool(value: Any) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "缺失"


def fmt_pct(value: Any) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "缺失"


def fmt_money(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "缺失"
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿元"
    if abs(value) >= 10_000:
        return f"{value / 10_000:.2f} 万元"
    return f"{value:.2f} 元"


def fmt_number(value: Any) -> str:
    return f"{value:.2f}" if isinstance(value, (int, float)) else "缺失"


def current_price(stock: dict[str, Any], factors: dict[str, Any]) -> float | None:
    for value in [
        stock.get("current_price"),
        stock.get("price"),
        factors.get("current_price"),
        factors.get("latest_price"),
        factors.get("close"),
    ]:
        if isinstance(value, (int, float)):
            return float(value)
    quote = stock.get("quote")
    if isinstance(quote, dict) and isinstance(quote.get("current_price"), (int, float)):
        return float(quote["current_price"])
    return None


def normalize_events(events: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        title = event.get("title") or event.get("name") or event.get("summary")
        if not title:
            continue
        normalized.append(
            {
                "date": event.get("date") or event.get("publish_date") or event.get("announcement_date"),
                "title": str(title),
                "impact": event.get("impact", "neutral"),
                "severity": event.get("severity", "medium"),
                "source": event.get("source", ""),
                "url": event.get("url", ""),
            }
        )
    return normalized[:8]


def build_key_metrics(stock: dict[str, Any], factors: dict[str, Any]) -> list[dict[str, str]]:
    kline = stock.get("kline_source")
    kline_summary = "缺失"
    if isinstance(kline, dict) and kline:
        kline_summary = (
            f"{kline.get('source', '未知来源')}：{kline.get('rows', '未知')} 条，"
            f"{kline.get('start_date', '未知')} 至 {kline.get('end_date', '未知')}"
        )
    events = stock.get("events") if isinstance(stock.get("events"), list) else []
    return [
        {"name": "当前价格", "value": fmt_number(current_price(stock, factors))},
        {"name": "K线来源", "value": kline_summary},
        {"name": "公告/事件数量", "value": str(len(events))},
        {"name": "20日涨跌幅", "value": fmt_pct(factors.get("pct_change_20d"))},
        {"name": "20日均额", "value": fmt_money(factors.get("amount_ma20"))},
        {"name": "价格站上20日线", "value": fmt_bool(factors.get("close_above_ma20"))},
        {"name": "20日线向上", "value": fmt_bool(factors.get("ma20_up"))},
        {"name": "价格站上60日线", "value": fmt_bool(factors.get("close_above_ma60"))},
        {"name": "20日线高于60日线", "value": fmt_bool(factors.get("ma20_above_ma60"))},
        {"name": "20日突破", "value": fmt_bool(factors.get("breakout_20d"))},
        {"name": "PE-TTM快照", "value": fmt_number(factors.get("pe_ttm_snapshot"))},
        {"name": "ROE-TTM", "value": fmt_pct(factors.get("roe_ttm"))},
        {"name": "营收同比", "value": fmt_pct(factors.get("revenue_yoy"))},
        {"name": "净利润同比", "value": fmt_pct(factors.get("net_profit_yoy"))},
        {"name": "PE三年分位", "value": fmt_pct(factors.get("pe_percentile_3y"))},
        {"name": "PB-LF", "value": fmt_number(factors.get("pb_lf"))},
        {"name": "PB三年分位", "value": fmt_pct(factors.get("pb_percentile_3y"))},
    ]


def build_reasons(stock: dict[str, Any], factors: dict[str, Any], dimensions: dict[str, float]) -> list[str]:
    reasons: list[str] = []
    price = current_price(stock, factors)
    if price is not None:
        reasons.append(f"已记录当前价格 {price:.2f}，便于候选池复盘时核对价格位置。")
    amount_ma20 = factors.get("amount_ma20")
    if isinstance(amount_ma20, (int, float)):
        reasons.append(f"近20日平均成交额约 {fmt_money(amount_ma20)}，满足本轮流动性初筛要求。")
    kline = stock.get("kline_source")
    if isinstance(kline, dict) and kline.get("source"):
        reasons.append(f"K线趋势已由 {kline.get('source')} 补充，覆盖 {kline.get('rows', '未知')} 条记录。")
    if factors.get("close_above_ma20") and factors.get("ma20_up"):
        reasons.append("价格位于20日均线上方且20日均线向上，短线趋势结构偏强。")
    if factors.get("close_above_ma60") and factors.get("ma20_above_ma60"):
        reasons.append("价格站上60日均线且20日均线高于60日均线，中期结构相对占优。")
    if factors.get("breakout_20d"):
        reasons.append("出现20日区间突破信号，短期资金推动较前期增强。")
    pe = factors.get("pe_ttm_snapshot")
    if isinstance(pe, (int, float)):
        reasons.append(f"已记录 PE-TTM 快照约 {pe:.2f}，可作为后续估值复核基准。")
    if not reasons:
        best = max(dimensions, key=dimensions.get)
        labels = {
            "trend_volume_price": "趋势与量价",
            "fundamental_quality": "基本面质量",
            "valuation": "估值水平",
            "event": "公告/事件",
            "risk": "风险因子",
        }
        reasons.append(f"当前相对较强维度为{labels.get(best, best)}，但仍需补充数据复核。")
    return list(dict.fromkeys(reasons))[:5]


def build_risks(stock: dict[str, Any], factors: dict[str, Any], data_quality: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    missing = set(str(item) for item in data_quality.get("missing_fields", []) if item)
    if {"roe_ttm", "revenue_yoy", "net_profit_yoy"} & missing:
        risks.append("基本面字段仍不完整，盈利质量判断可靠性较低。")
    if {"pe_percentile_3y", "pb_percentile_3y"} & missing:
        risks.append("估值分位缺失，无法判断当前估值处在历史高位还是低位。")
    if "announcements" in missing or "events" in missing:
        risks.append("公告/事件数据缺失，尚未排查减持、问询、处罚、业绩预告等事件冲击。")
    pct_change_20d = factors.get("pct_change_20d")
    if isinstance(pct_change_20d, (int, float)) and pct_change_20d > 0.35:
        risks.append(f"近20日涨幅约 {fmt_pct(pct_change_20d)}，短期追高和交易拥挤风险上升。")
    if factors.get("overheated_turnover") is True:
        risks.append("换手率或短期成交热度偏高，需警惕放量滞涨后的波动放大。")
    if factors.get("close_above_ma60") is False:
        risks.append("价格尚未站上60日均线，中期趋势仍未确认。")
    if factors.get("breakdown_ma60_with_volume") is True:
        risks.append("出现放量跌破60日均线特征，趋势风险优先级高于其他正面信号。")
    if factors.get("high_volume_stalling") is True:
        risks.append("存在放量滞涨迹象，资金分歧可能正在扩大。")
    if not risks:
        risks.append("未识别到单项硬性回避风险，但仍需跟踪财报、估值分位、公告和市场风格变化。")
    return list(dict.fromkeys(risks))[:5]


def build_valid_conditions(factors: dict[str, Any], data_quality: dict[str, Any]) -> list[str]:
    conditions = []
    conditions.append("价格维持在20日均线附近或上方，且20日均线未由升转降。")
    conditions.append("未新增 ST、退市风险、监管处罚、重大诉讼或严重流动性风险。")
    if data_quality.get("missing_fields"):
        conditions.append("补齐基本面、估值分位和公告数据后，未触发风险降级或回避规则。")
    else:
        conditions.append("后续财报、估值和公告数据与当前研究前提保持一致。")
    conditions.append("市场风格未显著切换到与候选池相反的防御或低波动风格。")
    return list(dict.fromkeys(conditions))[:5]


def build_invalid_conditions(factors: dict[str, Any], data_quality: dict[str, Any]) -> list[str]:
    conditions = [
        "跌破20日均线且成交额放大，短线趋势信号失效。",
        "有效跌破60日均线，或20日均线下穿60日均线，中期结构转弱。",
    ]
    if data_quality.get("missing_fields"):
        conditions.append("补充财务、估值分位或公告后出现负面结论，当前初筛评级需下调。")
    else:
        conditions.append("下一期财务或公告数据显著低于当前研究前提。")
    pct_change_20d = factors.get("pct_change_20d")
    if isinstance(pct_change_20d, (int, float)) and pct_change_20d > 0.35:
        conditions.append("高位持续放量但价格不能创新高，交易拥挤开始反噬。")
    else:
        conditions.append("成交额明显萎缩导致流动性初筛条件不再满足。")
    return conditions[:5]


def score_one(stock: dict[str, Any], weights: dict[str, float] | None) -> dict[str, Any]:
    factors = stock.get("factors", {})
    if not isinstance(factors, dict):
        factors = {}
    events = stock.get("events", [])
    if not isinstance(events, list):
        events = []
    normalized_events = normalize_events(events)
    data_quality = stock.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {"missing_fields": [], "quality_score": 0.7}

    dimensions = {
        "trend_volume_price": score_trend(factors),
        "fundamental_quality": score_fundamental(factors),
        "valuation": score_valuation(factors),
        "event": score_event(factors, normalized_events),
        "risk": score_risk(factors, data_quality),
    }
    total = weighted_score(dimensions, weights)
    rating = rating_from_score(total)
    result = {
        "symbol": stock.get("symbol"),
        "name": stock.get("name"),
        "industry": stock.get("industry", ""),
        "current_price": current_price(stock, factors),
        "rating": rating,
        "total_score": total,
        "confidence": round(float(data_quality.get("quality_score", 0.7)), 2),
        "dimension_scores": dimensions,
        "risk_flags": list(stock.get("risk_flags") or []),
        "events": normalized_events,
        "key_metrics": build_key_metrics(stock, factors),
        "core_reasons": build_reasons(stock, factors, dimensions),
        "risks": build_risks(stock, factors, data_quality),
        "valid_conditions": build_valid_conditions(factors, data_quality),
        "position_range": default_position_range(rating),
        "suitable_for": list(stock.get("suitable_for") or ["能理解研究信号不等于交易指令的投资者"]),
        "not_suitable_for": list(stock.get("not_suitable_for") or ["无法承受市场波动或需要确定性收益的投资者"]),
        "invalid_conditions": build_invalid_conditions(factors, data_quality),
        "data_quality": {
            "missing_fields": list(data_quality.get("missing_fields") or []),
            "quality_score": round(float(data_quality.get("quality_score", 0.7)), 2),
        },
    }
    adjusted = apply_risk_rules(result, stock)
    adjusted["position_range"] = default_position_range(adjusted["rating"])
    return adjusted


def build_signal(payload: dict[str, Any]) -> dict[str, Any]:
    stocks = payload.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        raise ValueError("input must contain a non-empty stocks list")

    weights = payload.get("weights")
    if weights is not None and not isinstance(weights, dict):
        weights = None

    results = [score_one(stock, weights) for stock in stocks if isinstance(stock, dict)]
    results.sort(key=lambda item: (item["rating"] == "鍥為伩", -float(item["total_score"])))
    risk_level = "high" if any(item.get("risk_level") in {"high", "extreme"} for item in results) else "medium"

    universe = payload.get("universe", {"market": "A股", "sector": None, "symbols": [], "filters": {}})
    if not isinstance(universe, dict):
        universe = {"market": "A股", "sector": None, "symbols": [], "filters": {}}
    universe = dict(universe)
    universe["symbols"] = [item.get("symbol") for item in results if item.get("symbol")]
    universe["stocks"] = [
        {
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "current_price": item.get("current_price"),
        }
        for item in results
    ]

    return {
        "as_of": payload.get("as_of"),
        "task_type": payload.get("task_type", "single_stock_diagnosis"),
        "universe": universe,
        "summary": {
            "market_view": payload.get("market_view", "基于输入因子生成结构化研究信号；未输入的数据不会被补造。"),
            "candidate_count": len(results),
            "risk_level": risk_level,
            "style_bias": payload.get("style_bias", []),
        },
        "results": results,
        "methodology_version": payload.get("methodology_version", METHODOLOGY_VERSION),
        "data_sources": payload.get("data_sources", ["user_provided_factor_json"]),
        "compliance_disclaimer": payload.get("compliance_disclaimer", DISCLAIMER),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: score_stock.py <input-factors.json> <output-signal.json>")
        return 2
    input_path = Path(argv[1])
    output_path = Path(argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    signal = build_signal(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(signal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {output_path}")
    print(f"results: {len(signal['results'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
