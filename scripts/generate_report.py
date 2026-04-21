#!/usr/bin/env python3
"""Generate a Markdown report from a validated signal JSON file."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from validate_signal_json import validate


def line_items(items: list[Any]) -> str:
    if not items:
        return "无"
    return "\n".join(f"{idx}. {item}" for idx, item in enumerate(items, start=1))


def metric_items(items: list[Any]) -> str:
    if not items:
        return "无"
    lines = []
    for item in items:
        if isinstance(item, dict):
            lines.append(f"- {item.get('name', '指标')}：{item.get('value', '缺失')}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


def format_percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "未给出"
    return f"{value * 100:.1f}%"


def format_price(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "缺失"
    return f"{value:.2f}"


def format_universe(universe: dict[str, Any]) -> str:
    stocks = universe.get("stocks")
    if isinstance(stocks, list) and stocks:
        labels = []
        for item in stocks:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol", "")
            name = item.get("name", "")
            price = format_price(item.get("current_price"))
            labels.append(f"{name}({symbol}, 当前价 {price})" if name else f"{symbol}(当前价 {price})")
        if labels:
            return ", ".join(labels)
    return ", ".join(universe.get("symbols") or []) or universe.get("market", "A股")


def event_items(items: list[Any]) -> str:
    if not items:
        return "无"
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        date = item.get("date") or "日期缺失"
        title = item.get("title") or item.get("name") or "公告标题缺失"
        impact = item.get("impact", "neutral")
        severity = item.get("severity", "medium")
        source = item.get("source", "")
        url = item.get("url")
        source_text = f"[{source}]({url})" if source and url else source or "来源缺失"
        lines.append(f"{date}｜{impact}/{severity}｜{title}｜{source_text}")
    return line_items(lines) if lines else "无"


def stock_section(item: dict[str, Any]) -> str:
    dims = item["dimension_scores"]
    position = item.get("position_range", {})
    return f"""## {item['name']}（{item['symbol']}）

研究评级：{item['rating']}  
综合评分：{item['total_score']}/100  
置信度：{item['confidence']}  
当前价格：{format_price(item.get('current_price'))}

### 评分拆解

| 维度 | 分数 |
|---|---:|
| 趋势与量价 | {dims['trend_volume_price']} |
| 基本面质量 | {dims['fundamental_quality']} |
| 估值水平 | {dims['valuation']} |
| 公告/事件 | {dims['event']} |
| 风险因子 | {dims['risk']} |

### 关键指标

{metric_items(item.get('key_metrics') or [])}

### 核心理由

{line_items(item['core_reasons'])}

### 主要风险

{line_items(item['risks'])}

### 公告/事件

{event_items(item.get('events') or [])}

### 生效条件

{line_items(item.get('valid_conditions') or [])}

### 适用人群

{', '.join(item.get('suitable_for') or [])}

### 不适用人群

{', '.join(item.get('not_suitable_for') or [])}

### 仓位区间

研究性观察仓位区间：{format_percent(position.get('min'))} - {format_percent(position.get('max'))}。该区间仅用于风险暴露管理，不构成交易指令。

### 失效条件

{line_items(item['invalid_conditions'])}
"""


def data_quality_section(payload: dict[str, Any]) -> str:
    field_counts: dict[str, int] = {}
    for item in payload["results"]:
        for field in item.get("data_quality", {}).get("missing_fields", []):
            field_counts[field] = field_counts.get(field, 0) + 1
    if not field_counts:
        return "## 数据质量与缺口\n\n结构化结果未记录字段缺口。\n"
    top = sorted(field_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    lines = [f"- `{field}`：{count} 只股票缺失" for field, count in top]
    return "\n".join(
        [
            "## 数据质量与缺口",
            "",
            "以下缺口来自结构化结果文件，报告不会用默认值补造这些字段：",
            "",
            *lines,
            "",
        ]
    )


def build_report(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    universe = payload.get("universe", {})
    sections = [
        "# A 股投资研究报告",
        "",
        f"数据截止日期：{payload['as_of']}",
        f"任务类型：{payload['task_type']}",
        f"股票池：{format_universe(universe)}",
        f"数据来源：{', '.join(payload.get('data_sources') or [])}",
        f"评分版本：{payload['methodology_version']}",
        "",
        "## 摘要",
        "",
        str(summary.get("market_view", "未提供市场摘要。")),
        "",
        f"候选数量：{summary.get('candidate_count', len(payload['results']))}",
        f"整体风险等级：{summary.get('risk_level', 'medium')}",
        "",
        data_quality_section(payload),
    ]
    for item in payload["results"]:
        sections.append(stock_section(item))
    sections.extend(
        [
            "## 合规提示",
            "",
            payload["compliance_disclaimer"],
            "",
            "本报告仅根据同名结构化 JSON 文件生成，未额外新增未经记录的数据事实。",
        ]
    )
    return "\n".join(sections)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: generate_report.py <signal.json> <report.md>")
        return 2
    signal_path = Path(argv[1])
    report_path = Path(argv[2])
    payload = json.loads(signal_path.read_text(encoding="utf-8"))
    errors = validate(payload)
    if errors:
        print("INVALID SIGNAL JSON")
        for error in errors:
            print(f"- {error}")
        return 1
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_report(payload), encoding="utf-8")
    print(f"WROTE {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
