# 数据字段设计

## 行情数据

| 字段 | 含义 |
|---|---|
| `trade_date` | 交易日期 |
| `symbol` | 股票代码，如 `600519.SH` |
| `name` | 股票名称 |
| `open` | 开盘价 |
| `high` | 最高价 |
| `low` | 最低价 |
| `close` | 收盘价 |
| `pre_close` | 昨收价 |
| `pct_change` | 涨跌幅 |
| `volume` | 成交量 |
| `amount` | 成交额 |
| `turnover_rate` | 换手率 |
| `amplitude` | 振幅 |
| `limit_up` | 是否涨停 |
| `limit_down` | 是否跌停 |
| `suspended` | 是否停牌 |
| `adj_factor` | 复权因子 |
| `market_cap` | 总市值 |
| `float_market_cap` | 流通市值 |

## 技术指标

| 字段 | 含义 |
|---|---|
| `ma5` / `ma10` / `ma20` / `ma60` / `ma120` | 均线 |
| `ema12` / `ema26` | 指数均线 |
| `macd_dif` / `macd_dea` / `macd_hist` | MACD |
| `rsi6` / `rsi14` | RSI |
| `atr14` | 平均真实波幅 |
| `vol_ma5` / `vol_ma20` | 成交量均线 |
| `amount_ma20` | 20 日平均成交额 |
| `high_20d` / `low_20d` | 20 日高低点 |
| `drawdown_60d` | 60 日最大回撤 |
| `relative_strength_20d` | 20 日相对强弱 |
| `breakout_20d` | 是否突破 20 日高点 |
| `price_position_120d` | 当前价格在 120 日区间位置 |

## 基本面数据

| 字段 | 含义 |
|---|---|
| `report_period` | 报告期 |
| `publish_date` | 披露日期，避免未来函数 |
| `revenue` | 营业收入 |
| `revenue_yoy` | 营收同比 |
| `net_profit` | 归母净利润 |
| `net_profit_yoy` | 归母净利润同比 |
| `deducted_net_profit` | 扣非净利润 |
| `deducted_net_profit_yoy` | 扣非净利润同比 |
| `gross_margin` | 毛利率 |
| `net_margin` | 净利率 |
| `roe` | 净资产收益率 |
| `roa` | 总资产收益率 |
| `operating_cash_flow` | 经营现金流 |
| `ocf_to_net_profit` | 经营现金流 / 净利润 |
| `debt_to_asset` | 资产负债率 |
| `inventory_turnover` | 存货周转率 |
| `accounts_receivable_turnover` | 应收账款周转率 |
| `eps` | 每股收益 |
| `bps` | 每股净资产 |

## 估值数据

| 字段 | 含义 |
|---|---|
| `pe_ttm` | 滚动市盈率 |
| `pb_lf` | 市净率 |
| `ps_ttm` | 市销率 |
| `pcf_ttm` | 市现率 |
| `dividend_yield` | 股息率 |
| `peg` | PEG |
| `pe_percentile_3y` | 近 3 年 PE 分位 |
| `pb_percentile_3y` | 近 3 年 PB 分位 |
| `industry_pe_percentile` | 行业内 PE 分位 |
| `industry_pb_percentile` | 行业内 PB 分位 |
| `valuation_zscore` | 估值标准分 |
| `earnings_yield` | 盈利收益率 |

## 公告/事件数据

| 字段 | 含义 |
|---|---|
| `announcement_id` | 公告 ID |
| `symbol` | 股票代码 |
| `title` | 公告标题 |
| `publish_time` | 发布时间 |
| `announcement_type` | 公告类型 |
| `raw_text` | 原文 |
| `event_type` | 事件类型 |
| `event_impact` | `positive` / `neutral` / `negative` |
| `event_severity` | `low` / `medium` / `high` |
| `event_confidence` | 事件解析置信度 |
| `event_summary` | 事件摘要 |
| `related_amount` | 涉及金额 |
| `related_ratio` | 涉及比例 |
| `effective_date` | 生效日期 |
| `expiry_date` | 影响截止日期 |

## 市场风格数据

| 字段 | 含义 |
|---|---|
| `index_code` | 指数代码 |
| `index_pct_change` | 指数涨跌幅 |
| `industry_code` | 行业代码 |
| `industry_name` | 行业名称 |
| `industry_pct_change` | 行业涨跌幅 |
| `industry_turnover` | 行业成交额 |
| `northbound_net_inflow` | 北向资金净流入 |
| `margin_balance_change` | 融资余额变化 |
| `market_breadth` | 上涨家数占比 |
| `limit_up_count` | 涨停数量 |
| `limit_down_count` | 跌停数量 |
| `style_value_return` | 价值风格收益 |
| `style_growth_return` | 成长风格收益 |
| `style_smallcap_return` | 小盘风格收益 |
| `style_largecap_return` | 大盘风格收益 |

## 用户偏好数据

| 字段 | 含义 |
|---|---|
| `risk_profile` | `conservative` / `stable` / `balanced` / `aggressive` |
| `investment_horizon` | `short_term` / `medium_term` / `long_term` |
| `preferred_industries` | 偏好行业 |
| `excluded_industries` | 排除行业 |
| `preferred_styles` | 偏好风格 |
| `max_drawdown_tolerance` | 最大回撤容忍 |
| `max_single_stock_weight` | 单股最大仓位 |
| `holding_symbols` | 当前持仓 |
| `watchlist_symbols` | 自选股 |
| `liquidity_requirement` | 流动性要求 |
| `avoid_st` | 是否回避 ST |
| `avoid_high_pledge` | 是否回避高质押 |
