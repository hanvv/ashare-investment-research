# 输入因子格式

`scripts/score_stock.py` 只接受已经获取或由用户提供的真实因子数据，不负责联网抓取，也不得补造缺失字段。

## 命令

```powershell
py scripts/score_stock.py inputs/{task_id}.factors.json outputs/{task_id}.signal.json
```

## 示例

```json
{
  "as_of": "2026-04-20",
  "task_type": "watchlist_tracking",
  "universe": {
    "market": "A股",
    "sector": null,
    "symbols": ["600000.SH"],
    "filters": {
      "exclude_st": true
    }
  },
  "data_sources": ["user_provided_factor_json"],
  "stocks": [
    {
      "symbol": "600000.SH",
      "name": "示例银行A",
      "industry": "银行",
      "factors": {
        "close_above_ma20": true,
        "ma20_up": true,
        "close_above_ma60": true,
        "ma60_up": true,
        "ma20_above_ma60": true,
        "relative_strength_20d": 0.72,
        "roe_ttm": 0.13,
        "revenue_yoy": 0.05,
        "net_profit_yoy": 0.08,
        "ocf_to_net_profit": 0.9,
        "pe_percentile_3y": 0.35,
        "pb_percentile_3y": 0.28
      },
      "events": [],
      "risk_flags": [],
      "data_quality": {
        "missing_fields": [],
        "quality_score": 0.95
      }
    }
  ]
}
```

## 支持的常用因子键

趋势与量价：

- `close_above_ma20`
- `ma20_up`
- `close_above_ma60`
- `ma60_up`
- `ma20_above_ma60`
- `breakout_20d`
- `relative_strength_20d`
- `pct_change_20d`
- `high_volume_stalling`
- `breakdown_ma60_with_volume`

基本面：

- `roe_ttm`
- `revenue_yoy`
- `net_profit_yoy`
- `ocf_to_net_profit`
- `gross_margin_stable_or_up`
- `high_debt_vs_industry`
- `receivable_inventory_abnormal`
- `deducted_profit_deterioration`

估值：

- `pe_percentile_3y`
- `pb_percentile_3y`
- `peg`
- `valuation_below_industry_with_quality`
- `high_valuation_slow_growth`
- `cyclical_low_pe_trap`

事件：

- `positive_earnings_guidance`
- `large_repurchase_cancel`
- `insider_increase`
- `major_contract`
- `shareholder_reduction`
- `regulatory_inquiry`
- `penalty`
- `negative_earnings_guidance`

风险：

- `is_st`
- `delisting_risk`
- `major_fraud_risk`
- `capital_occupation`
- `debt_default`
- `going_concern_uncertainty`
- `severe_illiquidity`
- `high_pledge`
- `overheated_turnover`
- `major_litigation`

## 缺失数据

缺失字段不得补造。将缺失字段写入：

```json
{
  "data_quality": {
    "missing_fields": ["pe_percentile_3y"],
    "quality_score": 0.82
  }
}
```
