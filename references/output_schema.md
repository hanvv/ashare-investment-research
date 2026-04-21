# 输出 Schema

结构化结果文件必须保存为 `outputs/{task_id}.signal.json`。

## 顶层字段

```json
{
  "as_of": "2026-04-20",
  "task_type": "single_stock_diagnosis",
  "universe": {
    "market": "A股",
    "sector": null,
    "symbols": ["600519.SH"],
    "filters": {}
  },
  "summary": {
    "market_view": "",
    "candidate_count": 1,
    "risk_level": "medium",
    "style_bias": ["质量"]
  },
  "results": [],
  "methodology_version": "ashare-research-signal-v1.1",
  "data_sources": ["user_provided_csv"],
  "compliance_disclaimer": "本结果基于公开数据和规则化评分模型生成，仅用于投资研究辅助，不构成任何收益承诺、买卖建议或个性化投顾服务。"
}
```

## `results[]` 字段

```json
{
  "symbol": "600519.SH",
  "name": "贵州茅台",
  "industry": "食品饮料",
  "rating": "关注",
  "total_score": 78,
  "confidence": 0.72,
  "dimension_scores": {
    "trend_volume_price": 75,
    "fundamental_quality": 86,
    "valuation": 62,
    "event": 70,
    "risk": 82
  },
  "risk_flags": [],
  "key_metrics": [
    {
      "name": "K线来源",
      "value": "akshare.stock_zh_a_daily，80 条，2025-12-17 至 2026-04-20"
    },
    {
      "name": "20日涨跌幅",
      "value": "23.9%"
    },
    {
      "name": "20日均额",
      "value": "103.94 亿元"
    },
    {
      "name": "价格站上20日线",
      "value": "是"
    }
  ],
  "core_reasons": [
    "近20日平均成交额满足本轮高流动性初筛要求。",
    "K线趋势已补充，报告不再仅依赖基础行情快照。",
    "价格位于20日均线上方且20日均线向上，短线趋势结构偏强。"
  ],
  "risks": [
    "基本面字段仍不完整，ROE、营收增速或净利润增速缺失会降低盈利质量判断的可靠性。",
    "估值分位缺失，当前只能使用PE快照，无法判断估值处于历史高位还是低位。",
    "公告/事件数据缺失，尚未排查减持、问询、处罚、业绩预告等事件冲击。"
  ],
  "valid_conditions": [
    "价格继续站稳20日均线，且20日均线不由升转降。",
    "价格不有效跌破60日均线，中期结构保持不破坏。",
    "补齐基本面、估值分位和公告数据后，未触发风险降级或回避规则。"
  ],
  "position_range": {
    "min": 0,
    "max": 0.05,
    "unit": "portfolio_weight"
  },
  "suitable_for": ["中长期", "稳健型"],
  "not_suitable_for": ["高频短线"],
  "invalid_conditions": [
    "跌破关键均线且成交放大。",
    "出现重大负面公告。"
  ],
  "data_quality": {
    "missing_fields": [],
    "quality_score": 0.95
  }
}
```

## 枚举

`task_type`：

- `market_scan`
- `sector_scan`
- `single_stock_diagnosis`
- `watchlist_tracking`
- `portfolio_review`

`rating`：

- `强关注`
- `关注`
- `观察`
- `中性`
- `回避`

`risk_level`：

- `low`
- `medium`
- `high`
- `extreme`

## 报告文件

Markdown 报告保存为 `outputs/{task_id}.report.md`，HTML 报告保存为 `outputs/{task_id}.report.html`，必须基于同名 `.signal.json` 生成。报告中不得出现 JSON 文件没有依据的新事实。

报告必须展示 `key_metrics`、`core_reasons`、`risks`、`valid_conditions` 和 `invalid_conditions`。如任一字段因数据缺失无法生成，应在结构化 JSON 中明确写入缺失原因，而不是在报告阶段补造。
