---
name: ashare-investment-research
description: 面向中国 A 股市场的智能投资研究 Skill。用于全市场盘后扫描、板块/主题筛选、单只股票诊断、自选股跟踪和组合观察；基于公开数据生成候选股票池、研究信号评级、核心理由、风险提示、仓位区间、适用人群和失效条件。必须先获取或读取真实数据，不得编造数据；必须将分析结果写入结构化文件，再基于该文件生成报告；不得只运行脚本后结束；不得输出自动交易、收益承诺、内幕消息或持牌投顾替代内容。
---

# A 股投资研究 Skill

## 核心定位

将公开数据、规则化评分、风险控制和自然语言解释结合起来，辅助个人投资者进行 A 股研究。输出是“研究辅助信号”，不是买卖指令、收益承诺、自动交易系统或个性化投顾服务。

## 强制约束

执行任何分析任务时必须遵守：

1. 不得编造数据、行情、财务指标、公告、估值或股票名称。没有数据时，明确说明缺失并降低置信度或停止生成结论。
2. 不得只运行脚本后结束。脚本只能作为数据处理、评分、校验或格式化工具；必须阅读关键结果并生成解释。
3. 必须先把分析结果写回结构化文件，再生成面向用户的报告。默认路径使用 `outputs/{task_id}.signal.json` 和 `outputs/{task_id}.report.md`。
4. 必须在报告中说明数据截止日期、数据来源、数据质量、评分版本和合规提示。
5. 必须同时输出关键指标、核心理由、主要风险、生效条件和失效条件；这些内容必须来自结构化 JSON，不得只在报告阶段临时编写。
6. 遇到 ST、退市风险、重大财务异常、重大监管处罚、严重流动性风险时，必须触发降级或回避规则。
7. 不得使用“必涨”“稳赚”“可以买入”“建议满仓”“目标价必达”等绝对化表达。
8. 仓位区间只能表述为风险暴露参考，不得作为交易指令。

## 标准工作流

1. 识别任务类型：`market_scan`、`sector_scan`、`single_stock_diagnosis`、`watchlist_tracking` 或 `portfolio_review`。
2. 明确股票池、日期、用户偏好、风险偏好和输出格式。
3. 获取或读取真实数据；按数据类型选择主源：实时行情/PE/市值优先东方财富 push2，财报历史和 K 线优先 AkShare，公告/研报优先巨潮 cninfo + AkShare；失败时按数据源策略降级并记录 `as_of`。
4. 校验数据完整性；缺失关键字段时降低置信度，严重缺失时拒绝给高评级。
5. 执行股票池过滤：ST、退市风险、停牌、低流动性、新股数据不足等。
6. 计算趋势与量价、基本面质量、估值、公告事件、风险因子，并生成 `key_metrics`、`core_reasons`、`risks`、`valid_conditions`、`invalid_conditions`。
7. 合成评分并映射评级。
8. 运行风险控制复核，应用一票回避和强制降级规则。
9. 写入结构化 JSON 结果文件。
10. 运行 `scripts/validate_signal_json.py` 校验结构化结果。
11. 基于已写入并校验通过的 JSON 生成 Markdown 报告。
12. 向用户返回报告摘要、文件路径、关键风险和验证结果。

## 任务模式

### 全市场盘后扫描

用于从 A 股全市场或指定交易板块中筛选候选股票。默认剔除 ST、退市风险、长期停牌、低流动性和上市时间过短标的。输出 Top N 候选池、行业分布、风格偏向、风险集中度和每只股票的核心理由。

### 板块/主题筛选

用于行业、概念、指数成分或用户给定主题的内部排序。必须说明板块热度、资金拥挤度、龙头/补涨/滞涨分类和主题持续性的不确定性。

### 单只股票诊断

用于诊断指定股票的趋势、基本面、估值、公告事件和风险。必须输出研究评级、评分拆解、适用人群、风险提示和失效条件。

### 自选股跟踪

用于每日或定期跟踪用户自选股。必须识别评级变化、风险新增、信号改善和优先复盘名单。

### 组合观察

用于分析持仓或观察组合。必须关注行业集中度、风格暴露、单股风险、仓位集中和优先复盘顺序。

## 评分框架

默认总分 0-100：

- 趋势与量价：30%
- 基本面质量：25%
- 估值水平：15%
- 公告/事件驱动：15%
- 风险因子：15%

评级映射：

- 85-100：强关注
- 75-84：关注
- 65-74：观察
- 50-64：中性
- 0-49：回避

风险规则优先于评分。严重风险可以覆盖总分结果，将评级限制为“观察”“中性”或“回避”。

## 结构化文件要求

每次分析至少生成：

- `outputs/{task_id}.signal.json`：结构化研究信号，字段参考 `references/output_schema.md`。
- `outputs/{task_id}.report.md`：面向用户的 Markdown 报告。
- `outputs/{task_id}.report.html`：面向用户的静态 HTML 报告，页面简洁、美观、可本地直接打开。

推荐额外生成：

- `outputs/{task_id}.data_quality.json`：字段缺失、数据来源、异常值、可用日期。
- `outputs/{task_id}.audit.json`：评分版本、工具调用、参数、风险规则命中。

在最终回复中列出生成文件路径和校验状态。

## 何时读取参考文档

- 字段设计：读取 `references/data_dictionary.md`。
- 数据源优先级和降级策略：读取 `references/data_source_policy.md`。
- 评分细则和风险规则：读取 `references/scoring_methodology.md`。
- 合规边界和禁用话术：读取 `references/compliance_policy.md`。
- JSON 输出结构：读取 `references/output_schema.md`。
- 输入因子格式：读取 `references/input_factor_format.md`。
- 内部 Prompt：读取 `references/prompt_templates.md`。
- 工具接口：读取 `references/tool_contracts.md`。

## 校验

生成结构化 JSON 后运行：

```powershell
py scripts/validate_signal_json.py outputs/{task_id}.signal.json
```

如果环境没有 `py`，可用任意 Python 3 解释器运行该脚本。校验失败时必须修复 JSON，再生成报告。

## 可执行脚本

- `scripts/score_stock.py <input-factors.json> <output-signal.json>`：从真实输入因子生成结构化研究信号。输入数据缺失时只能记录缺失和降低置信度，不得补造；必须把关键指标、核心理由、主要风险、生效条件和失效条件写入结构化结果。
- `scripts/fetch_akshare_snapshot.py <output-factors.json>`：使用 AkShare 获取 A 股行情快照并生成因子输入文件。主要用于 K 线/行情补充或 push2 不可用后的低置信兜底；完整数据源优先级见 `references/data_source_policy.md`。
- `scripts/fetch_tencent_snapshot.py <output-factors.json>`：当 push2 和雪球不可用时，使用腾讯基础行情备源生成低置信流动性初筛输入。
- `scripts/enrich_akshare_kline.py <input-factors.json> <output-factors.json>`：对候选池补充 AkShare 日 K 线趋势因子，减少仅靠基础行情导致的指标缺口。
- `scripts/apply_risk_rules.py <result.json> <stock.json> <output.json>`：对单股评分结果应用一票回避和强制降级规则。
- `scripts/validate_signal_json.py <output-signal.json>`：校验结构化结果是否满足最低 Schema。
- `scripts/generate_report.py <output-signal.json> <output-report.md>`：基于已校验的结构化 JSON 生成 Markdown 报告，不得新增 JSON 中没有的数据事实。
- `scripts/generate_html_report.py <output-signal.json> <output-report.html>`：基于已校验的结构化 JSON 生成静态 HTML 报告，不得新增 JSON 中没有的数据事实。

最小闭环：

```powershell
py scripts/score_stock.py inputs/{task_id}.factors.json outputs/{task_id}.signal.json
py scripts/validate_signal_json.py outputs/{task_id}.signal.json
py scripts/generate_report.py outputs/{task_id}.signal.json outputs/{task_id}.report.md
py scripts/generate_html_report.py outputs/{task_id}.signal.json outputs/{task_id}.report.html
```
