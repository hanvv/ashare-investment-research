# A 股投资研究 Skill

面向中国 A 股市场的投资研究辅助 Skill。它把公开行情、K 线、基本面、估值、公告事件和风险规则整理成结构化信号文件，再生成 Markdown / HTML 报告。

> 本项目只输出研究辅助信号，不提供自动交易、收益承诺、内幕消息或持牌投顾替代服务。

[用法](#用法) · [工作流](#工作流) · [候选排序逻辑](#候选排序逻辑) · [数据源](#数据源) · [脚本说明](#脚本说明) · [项目结构](#项目结构) · [合规边界](#合规边界)

## 这是啥

一句话：给定 A 股股票池或全市场扫描条件，生成一份可审计的候选股研究报告。

当前能力包括：

- 全市场盘后初筛：按流动性、ST/退市风险等硬条件生成候选池。
- 候选池增强：补充 K 线趋势、基本面、估值分位、当前价格、公告/事件。
- 规则化评分：按趋势与量价、基本面质量、估值、公告/事件、风险因子打分。
- 风险复核：遇到 ST、退市风险、处罚、严重流动性问题等触发降级或回避。
- 报告输出：生成结构化 JSON、Markdown 报告和可本地打开的 HTML 报告。
- 数据缺口显式记录：拿不到的数据写入 `data_quality.missing_fields`，不使用默认值补造。

## 安装 / 启用 Skill

这是一个 Codex skill，不是普通 Python 包。Codex 发现 skill 的方式是读取 `$CODEX_HOME/skills/<skill-name>/SKILL.md`。本项目的 skill 名称是：

```text
ashare-investment-research
```

### 方式一：放入 Codex skills 目录

将整个目录放到 Codex skills 目录下：

```text
$CODEX_HOME/skills/ashare-investment-research
```

如果没有设置 `CODEX_HOME`，通常使用：

```text
~/.codex/skills/ashare-investment-research
```

在 Windows 上，本机当前安装路径示例是：

```text
C:\Users\vv\.codex\skills\ashare-investment-research
```

目录内必须保留：

```text
ashare-investment-research/
├── SKILL.md
├── agents/
├── references/
└── scripts/
```

安装后，向 Codex 提出 A 股全市场扫描、单股诊断、自选股跟踪、公告事件补充、报告生成等请求时，会触发这个 skill。

### 方式二：通过 skill-installer 安装

如果你使用 Codex 的 `skill-installer` 工作流，可以让 Codex 从仓库或本地目录安装到 `$CODEX_HOME/skills`。安装完成后确认目录名仍为：

```text
ashare-investment-research
```

### 脚本运行依赖

skill 本身的触发不需要 `pip install`。只有在运行 bundled scripts 抓取和增强数据时，才需要 Python 依赖。

建议使用 Python 3.9+。AkShare 相关脚本需要：

```powershell
py -m pip install akshare pandas
```

网络受限时可以使用国内镜像：

```powershell
py -m pip install akshare pandas -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 用法

### 在 Codex 中使用

安装到 skills 目录后，不需要手动 import 或执行入口命令。直接向 Codex 提出 A 股研究任务即可，Codex 会在匹配到任务时读取 `SKILL.md`，再按需调用 `scripts/` 和 `references/`。

示例请求：

```text
用 ashare-investment-research 做一次 A 股全市场盘后扫描，剔除 ST，最小成交额 10 亿元，输出 Top 30，补充当前价格和近 90 天公告事件，生成 Markdown 和 HTML 报告。
```

```text
诊断 300750.SZ 宁德时代，补充 K 线、估值、基本面、当前价和公告事件，给出研究评级、核心理由、风险、失效条件和数据缺口。
```

```text
跟踪我的自选股：002475.SZ、300308.SZ、601138.SH。更新当前价格和公告事件，指出评级变化和需要优先复盘的股票。
```

```text
基于现有 outputs/market_scan_20260420_uzi_fv_quote_events.signal.json 重新生成 HTML 报告，并让公告事件来源显示为可点击链接。
```

Codex 执行时应遵守两个原则：

- 先获取或读取真实数据，再写结构化 JSON，最后从 JSON 生成报告。
- 不能只运行脚本后结束；需要检查关键结果、说明数据来源、缺口、风险和生成文件。

### 手动脚本闭环

如果你要调试脚本、复现实验结果，或在 Codex 外部运行，可以使用下面的命令。

已有因子文件时，直接评分、校验并生成报告：

```powershell
py scripts/score_stock.py inputs/{task_id}.factors.json outputs/{task_id}.signal.json
py scripts/validate_signal_json.py outputs/{task_id}.signal.json
py scripts/generate_report.py outputs/{task_id}.signal.json outputs/{task_id}.report.md
py scripts/generate_html_report.py outputs/{task_id}.signal.json outputs/{task_id}.report.html
```

### 手动全市场扫描示例

使用腾讯行情备源做全市场流动性初筛，默认剔除 ST/退市字样股票，并按成交额优先选出候选池：

```powershell
py scripts/fetch_tencent_snapshot.py inputs/market_scan.factors.json --limit 30 --min-amount 1000000000
```

随后补充 K 线、基本面、估值、当前价格、公告事件：

```powershell
py scripts/enrich_akshare_kline.py inputs/market_scan.factors.json inputs/market_scan.kline.json
py scripts/enrich_akshare_fundamental_valuation.py inputs/market_scan.kline.json inputs/market_scan.fv.json
py scripts/enrich_tencent_quote.py inputs/market_scan.fv.json inputs/market_scan.quote.json
py scripts/enrich_cninfo_announcements.py inputs/market_scan.quote.json inputs/market_scan.events.json --lookback-days 90 --page-size 10
```

最后生成结构化信号和报告：

```powershell
py scripts/score_stock.py inputs/market_scan.events.json outputs/market_scan.signal.json
py scripts/validate_signal_json.py outputs/market_scan.signal.json
py scripts/generate_report.py outputs/market_scan.signal.json outputs/market_scan.report.md
py scripts/generate_html_report.py outputs/market_scan.signal.json outputs/market_scan.report.html
```

## 工作流

```text
行情初筛
  -> K 线趋势补充
  -> 基本面 / 估值补充
  -> 当前价格补充
  -> 公告 / 事件补充
  -> 规则化评分
  -> 风险规则复核
  -> JSON 校验
  -> Markdown / HTML 报告
```

每一步都只写入真实拿到的数据。失败时记录审计信息和缺失字段，不生成虚假事实。

## 候选排序逻辑

当前实现是两段式：

1. **全市场初筛**  
   `fetch_tencent_snapshot.py` / `fetch_akshare_snapshot.py` 先从全市场行情快照中剔除 ST、退市字样和低成交额股票，再按成交额优先、涨跌幅次之取前 `limit` 只。

   ```python
   stocks.sort(key=lambda item: (item["_amount"], item["_pct_change"]), reverse=True)
   ```

2. **候选池内部排序**  
   `score_stock.py` 只对已经入池的股票做综合评分排序。报告中的“候选排序”就是 `signal.json` 里的 `results` 顺序。

也就是说，当前报告不是“全市场所有股票都补齐完整因子后综合排名”，而是“先按流动性等硬条件选出候选池，再在候选池内做研究排序”。

如果需要真正的全市场综合筛选，建议把初筛 `limit` 放大到 Top 100 / Top 200，再对扩大后的股票池补全 K 线、基本面、估值和公告事件，最后输出 Top 30。

## 评分框架

默认总分 0-100：

| 维度 | 权重 |
|---|---:|
| 趋势与量价 | 30% |
| 基本面质量 | 25% |
| 估值水平 | 15% |
| 公告/事件 | 15% |
| 风险因子 | 15% |

评级映射由 `apply_risk_rules.py` 提供，并且风险规则优先于分数。严重风险可以覆盖总分结果，直接降级或标记回避。

## 数据源

| 数据 | 当前主用来源 | 说明 |
|---|---|---|
| 实时行情 / 当前价 | 腾讯 `qt.gtimg.cn` | 用于候选池初筛和当前价格补充 |
| A 股行情快照 | AkShare `stock_zh_a_spot_em` | 可作为行情快照备源 |
| K 线 | AkShare / 新浪 / 腾讯 fallback | 生成均线、突破、成交额等趋势因子 |
| 基本面 | AkShare `stock_financial_analysis_indicator` | ROE、营收同比、净利润同比等 |
| 估值 | AkShare `stock_zh_valuation_baidu` | PE/PB 及近三年分位 |
| 公告 / 事件 | 巨潮资讯 `cninfo.com.cn` | 近 N 天公告标题、PDF 链接、事件关键词分类 |

数据源不可用时，脚本会记录失败原因。报告中不会把缺失数据当成真实数据展示。

## 输出文件

标准输出文件：

- `outputs/{task_id}.signal.json`：结构化研究信号，作为唯一事实来源。
- `outputs/{task_id}.report.md`：Markdown 报告。
- `outputs/{task_id}.report.html`：静态 HTML 报告，可直接本地打开。

增强输入文件通常放在 `inputs/` 下，例如：

- `*.factors.json`
- `*.kline.json`
- `*.fv.json`
- `*.quote.json`
- `*.events.json`

## 脚本说明

| 脚本 | 作用 |
|---|---|
| `fetch_tencent_snapshot.py` | 使用腾讯行情做全市场流动性初筛 |
| `fetch_akshare_snapshot.py` | 使用 AkShare 生成行情快照初筛输入 |
| `enrich_akshare_kline.py` | 补充 K 线和趋势量价因子 |
| `enrich_akshare_fundamental_valuation.py` | 补充基本面与估值分位 |
| `enrich_tencent_quote.py` | 给已有候选池补充当前价格和行情快照 |
| `enrich_cninfo_announcements.py` | 补充巨潮公告/事件，带来源 PDF 链接 |
| `score_stock.py` | 生成结构化研究信号 |
| `apply_risk_rules.py` | 应用一票回避和强制降级规则 |
| `validate_signal_json.py` | 校验结构化信号 JSON |
| `generate_report.py` | 从 JSON 生成 Markdown 报告 |
| `generate_html_report.py` | 从 JSON 生成 HTML 报告 |

## 项目结构

```text
ashare-investment-research/
├── SKILL.md
├── README.md
├── agents/
├── inputs/
├── outputs/
├── references/
│   ├── compliance_policy.md
│   ├── data_dictionary.md
│   ├── data_source_policy.md
│   ├── input_factor_format.md
│   ├── output_schema.md
│   ├── prompt_templates.md
│   ├── scoring_methodology.md
│   └── tool_contracts.md
└── scripts/
    ├── fetch_tencent_snapshot.py
    ├── fetch_akshare_snapshot.py
    ├── enrich_akshare_kline.py
    ├── enrich_akshare_fundamental_valuation.py
    ├── enrich_tencent_quote.py
    ├── enrich_cninfo_announcements.py
    ├── score_stock.py
    ├── apply_risk_rules.py
    ├── validate_signal_json.py
    ├── generate_report.py
    └── generate_html_report.py
```

## 数据缺口怎么处理

脚本不会补造缺失数据。缺失字段会进入：

```json
{
  "data_quality": {
    "missing_fields": ["pe_percentile_3y", "announcements"],
    "quality_score": 0.72
  }
}
```

报告会显示数据缺口，并通过置信度影响最终研究信号。公告/事件、当前价、估值分位等字段缺失时，应先补数据再解读排序结果。

## 合规边界

本项目输出的是研究辅助材料，不是交易系统。

明确不做：

- 不输出“必涨”“稳赚”“可以买入”“满仓”“目标价必达”等确定性表述。
- 不承诺收益。
- 不替代持牌投顾服务。
- 不根据内幕消息生成结论。
- 不自动下单或提供自动交易执行。

仓位区间仅用于风险暴露讨论，不构成交易指令。
