# 工具与接口契约

## `get_market_data`

入参：

```json
{
  "symbols": ["600519.SH"],
  "start_date": "2025-01-01",
  "end_date": "2026-04-20",
  "frequency": "daily",
  "adjust": "qfq",
  "fields": ["open", "high", "low", "close", "volume", "amount", "turnover_rate"]
}
```

出参：

```json
{
  "as_of": "2026-04-20",
  "records": []
}
```

## `get_fundamental_data`

入参：

```json
{
  "symbols": ["600519.SH"],
  "periods": 8,
  "fields": ["revenue_yoy", "net_profit_yoy", "roe", "gross_margin", "operating_cash_flow"]
}
```

出参：

```json
{
  "records": []
}
```

## `get_valuation_data`

入参：

```json
{
  "symbols": ["600519.SH"],
  "as_of": "2026-04-20",
  "lookback_years": 3,
  "fields": ["pe_ttm", "pb_lf", "ps_ttm", "pe_percentile_3y", "pb_percentile_3y"]
}
```

出参：

```json
{
  "records": []
}
```

## `get_announcements`

入参：

```json
{
  "symbols": ["600519.SH"],
  "start_date": "2026-01-01",
  "end_date": "2026-04-20",
  "types": ["earnings", "reduction", "repurchase", "regulatory", "litigation"]
}
```

出参：

```json
{
  "records": []
}
```

## `parse_event_signal`

入参：

```json
{
  "announcement_id": "ann_001",
  "title": "关于控股股东减持计划的公告",
  "raw_text": "..."
}
```

出参：

```json
{
  "event_type": "shareholder_reduction",
  "impact": "negative",
  "severity": "medium",
  "confidence": 0.86,
  "summary": "控股股东拟减持不超过总股本 2%。"
}
```

## `calculate_factors`

入参：

```json
{
  "market_data": {},
  "fundamental_data": {},
  "valuation_data": {},
  "event_data": {}
}
```

出参：

```json
{
  "symbol": "600519.SH",
  "factors": {}
}
```

## `score_stock`

入参：

```json
{
  "symbol": "600519.SH",
  "factors": {},
  "weights": {
    "trend_volume_price": 0.3,
    "fundamental_quality": 0.25,
    "valuation": 0.15,
    "event": 0.15,
    "risk": 0.15
  }
}
```

出参：

```json
{
  "symbol": "600519.SH",
  "total_score": 78,
  "dimension_scores": {}
}
```

## `apply_risk_rules`

入参：

```json
{
  "symbol": "600519.SH",
  "initial_rating": "关注",
  "initial_score": 78,
  "risk_events": [],
  "risk_factors": {}
}
```

出参：

```json
{
  "final_rating": "关注",
  "final_score": 78,
  "risk_level": "medium",
  "downgraded": false,
  "avoid": false,
  "risk_reasons": []
}
```

## `rank_stocks`

入参：

```json
{
  "scored_stocks": [],
  "user_profile": {},
  "ranking_method": "score_then_risk_adjusted"
}
```

出参：

```json
{
  "ranked_results": []
}
```

## `generate_explanation`

入参：

```json
{
  "task_type": "single_stock_diagnosis",
  "signal_json_path": "outputs/task.signal.json",
  "language": "zh-CN"
}
```

出参：

```json
{
  "report_path": "outputs/task.report.md"
}
```

## 本地脚本契约

### `scripts/fetch_akshare_snapshot.py`

用途：使用 AkShare 获取 A 股行情快照，并生成 `score_stock.py` 可读取的因子输入 JSON。根据数据源策略，实时行情/PE/市值的完整主源应优先使用东方财富 push2；本脚本适合作为 AkShare 路径或低置信兜底输入生成器。

命令：

```powershell
py scripts/fetch_akshare_snapshot.py inputs/{task_id}.factors.json --limit 30 --min-amount 100000000
```

输出：`inputs/{task_id}.factors.json`。

约束：

- 记录来源为 AkShare；若用于实时行情筛选，必须说明 push2 不可用或用户明确指定 AkShare。
- 缺少基本面、估值和公告时必须写入 `data_quality.missing_fields`。
- 不得用行情快照伪装成完整多维研究。

### `scripts/score_stock.py`

用途：从真实输入因子生成结构化研究信号文件。

命令：

```powershell
py scripts/score_stock.py inputs/{task_id}.factors.json outputs/{task_id}.signal.json
```

输入：符合 `references/input_factor_format.md` 的因子 JSON。

输出：符合 `references/output_schema.md` 的 `signal.json`。

约束：

- 不联网抓取。
- 不补造缺失字段。
- 缺失字段写入 `data_quality.missing_fields`。
- 根据 `data_quality.quality_score` 调整置信度。
- 必须生成 `key_metrics`、`core_reasons`、`risks`、`valid_conditions`、`invalid_conditions`，报告只能读取这些结构化字段。

### `scripts/enrich_akshare_kline.py`

用途：对已有因子输入文件补充日 K 线趋势因子，包括 MA20、MA60、均线方向、20 日突破、20 日涨幅和 20 日成交额均值。调用方式参考本地 `a-stock-quant/data/fetchers/history_fetcher.py` 的 AkShare 逻辑，并参考 UZI-Skill 的 A 股 K 线 fallback 链：AkShare 东财 -> AkShare 新浪 -> 新浪 K 线直连 -> 腾讯 ifzq K 线直连。

命令：

```powershell
py scripts/enrich_akshare_kline.py inputs/{task_id}.factors.json inputs/{task_id}.factors.enriched.json --days 120
```

约束：

- 只补充真实返回的 K 线指标。
- 不读取或依赖 `a-stock-quant` 的 sqlite 缓存。
- 使用前复权 `qfq`。
- 获取失败时写入 `data_quality.missing_fields`，不得补造。
- 成功补充 K 线后可适度提高 `data_quality.quality_score`，但若仍缺少财务、估值分位和公告，置信度仍应保持克制。

### `scripts/apply_risk_rules.py`

用途：对单股评分结果执行一票回避和强制降级。

命令：

```powershell
py scripts/apply_risk_rules.py result.json stock.json adjusted_result.json
```

输出：带 `risk_flags`、`risk_level`、`avoid`、`downgraded` 的单股结果。

### `scripts/validate_signal_json.py`

用途：校验结构化结果文件是否满足最低 Schema。

命令：

```powershell
py scripts/validate_signal_json.py outputs/{task_id}.signal.json
```

输出：`VALID` 或 `INVALID` 及错误列表。

### `scripts/generate_report.py`

用途：基于已校验的结构化 JSON 生成 Markdown 报告。

命令：

```powershell
py scripts/generate_report.py outputs/{task_id}.signal.json outputs/{task_id}.report.md
```

约束：

- 报告只能使用 `signal.json` 中已有事实。
- 生成前会再次调用 JSON 校验逻辑。
- 校验失败时不生成报告。

### `scripts/generate_html_report.py`

用途：基于已校验的结构化 JSON 生成静态 HTML 报告。

命令：

```powershell
py scripts/generate_html_report.py outputs/{task_id}.signal.json outputs/{task_id}.report.html
```

约束：

- 页面必须能本地直接打开，不依赖外部 CDN、字体、脚本或图片。
- 报告只能使用 `signal.json` 中已有事实。
- 生成前会再次调用 JSON 校验逻辑。
- 校验失败时不生成报告。
- 页面设计保持简洁、美观，突出摘要、候选排序、评分拆解、关键指标、核心理由、风险、生效条件和失效条件。
