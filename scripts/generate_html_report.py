#!/usr/bin/env python3
"""Generate a static HTML report from a validated signal JSON file."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

from validate_signal_json import validate


RATING_CLASS = {
    "寮哄叧娉?": "rating-strong",
    "鍏虫敞": "rating-watch",
    "瑙傚療": "rating-observe",
    "涓€?": "rating-neutral",
    "鍥為伩": "rating-avoid",
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fmt_percent(value: Any) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "未给出"


def fmt_price(value: Any) -> str:
    return f"{value:.2f}" if isinstance(value, (int, float)) else "缺失"


def list_html(items: list[Any]) -> str:
    if not items:
        return "<li>无</li>"
    return "".join(f"<li>{esc(item)}</li>" for item in items)


def events_html(items: list[Any]) -> str:
    if not items:
        return "<li>无</li>"
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source = item.get("source") or "来源缺失"
        url = item.get("url")
        source_html = (
            f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(source)}</a>'
            if url
            else esc(source)
        )
        rows.append(
            f"<li><strong>{esc(item.get('date') or '日期缺失')}</strong> "
            f"{esc(item.get('impact', 'neutral'))}/{esc(item.get('severity', 'medium'))} "
            f"{esc(item.get('title') or '公告标题缺失')} "
            f"<span class=\"event-source\">{source_html}</span></li>"
        )
    return "".join(rows) or "<li>无</li>"


def key_metrics_html(items: list[Any]) -> str:
    if not items:
        return '<p class="muted">无关键指标记录</p>'
    chips = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name", "指标")
            value = item.get("value", "缺失")
        else:
            name = "指标"
            value = item
        chips.append(f"<span><em>{esc(name)}</em><strong>{esc(value)}</strong></span>")
    return f'<div class="metric-chips">{"".join(chips)}</div>'


def format_universe(universe: dict[str, Any]) -> str:
    stocks = universe.get("stocks")
    if isinstance(stocks, list) and stocks:
        labels = []
        for item in stocks:
            if isinstance(item, dict):
                labels.append(
                    f"{item.get('name', '')}({item.get('symbol', '')}, 当前价 {fmt_price(item.get('current_price'))})"
                )
        if labels:
            return ", ".join(labels)
    return ", ".join(universe.get("symbols") or []) or universe.get("market", "A股")


def metric_cards(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    return f"""
    <section class="metrics" aria-label="报告摘要指标">
      <div class="metric"><span>候选数量</span><strong>{esc(summary.get("candidate_count", len(payload["results"])))}</strong></div>
      <div class="metric"><span>整体风险</span><strong>{esc(summary.get("risk_level", "medium"))}</strong></div>
      <div class="metric"><span>数据来源</span><strong>{esc(", ".join(payload.get("data_sources") or []))}</strong></div>
      <div class="metric"><span>评分版本</span><strong>{esc(payload.get("methodology_version", ""))}</strong></div>
    </section>
    """


def ranking_table(results: list[dict[str, Any]]) -> str:
    rows = []
    for idx, item in enumerate(results, start=1):
        rating = item["rating"]
        klass = RATING_CLASS.get(rating, "rating-neutral")
        missing = item.get("data_quality", {}).get("missing_fields", [])
        rows.append(
            f"""
            <tr>
              <td>{idx}</td>
              <td><strong>{esc(item["name"])}</strong><br><span>{esc(item["symbol"])}</span></td>
              <td>{esc(fmt_price(item.get("current_price")))}</td>
              <td><span class="badge {klass}">{esc(rating)}</span></td>
              <td>{esc(item["total_score"])}</td>
              <td>{esc(item["confidence"])}</td>
              <td>{esc(", ".join(missing[:4]))}{' ...' if len(missing) > 4 else ''}</td>
            </tr>
            """
        )
    return f"""
    <section class="panel">
      <div class="panel-title">
        <h2>候选排序</h2>
        <p>按结构化信号文件中的排序展示，低置信结果仅代表初筛候选。</p>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>股票</th><th>当前价</th><th>评级</th><th>评分</th><th>置信度</th><th>主要缺失字段</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def score_bars(dims: dict[str, Any]) -> str:
    labels = [
        ("trend_volume_price", "趋势与量价"),
        ("fundamental_quality", "基本面质量"),
        ("valuation", "估值水平"),
        ("event", "公告/事件"),
        ("risk", "风险因子"),
    ]
    rows = []
    for key, label in labels:
        value = dims.get(key, 0)
        width = max(0, min(100, float(value))) if isinstance(value, (int, float)) else 0
        rows.append(
            f"""
            <div class="score-row">
              <span>{esc(label)}</span>
              <div class="bar"><i style="width:{width:.1f}%"></i></div>
              <strong>{esc(value)}</strong>
            </div>
            """
        )
    return "".join(rows)


def stock_cards(results: list[dict[str, Any]]) -> str:
    cards = []
    for item in results:
        rating = item["rating"]
        klass = RATING_CLASS.get(rating, "rating-neutral")
        position = item.get("position_range", {})
        cards.append(
            f"""
            <article class="stock-card">
              <header>
                <div>
                  <h3>{esc(item["name"])}</h3>
                  <p>{esc(item["symbol"])} {esc(item.get("industry", ""))}</p>
                </div>
                <span class="badge {klass}">{esc(rating)}</span>
              </header>
              <div class="stock-meta">
                <span>当前价 <strong>{esc(fmt_price(item.get("current_price")))}</strong></span>
                <span>综合评分 <strong>{esc(item["total_score"])}</strong></span>
                <span>置信度 <strong>{esc(item["confidence"])}</strong></span>
                <span>仓位参考 <strong>{fmt_percent(position.get("min"))} - {fmt_percent(position.get("max"))}</strong></span>
              </div>
              <div class="scores">{score_bars(item["dimension_scores"])}</div>
              <section><h4>关键指标</h4>{key_metrics_html(item.get("key_metrics") or [])}</section>
              <div class="grid-2">
                <section><h4>核心理由</h4><ol>{list_html(item["core_reasons"])}</ol></section>
                <section><h4>主要风险</h4><ol>{list_html(item["risks"])}</ol></section>
              </div>
              <section><h4>公告/事件</h4><ol>{events_html(item.get("events") or [])}</ol></section>
              <div class="grid-2">
                <section><h4>生效条件</h4><ol>{list_html(item.get("valid_conditions") or [])}</ol></section>
                <section><h4>失效条件</h4><ol>{list_html(item["invalid_conditions"])}</ol></section>
              </div>
            </article>
            """
        )
    return f'<section class="cards">{"".join(cards)}</section>'


def build_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    universe = payload.get("universe", {})
    symbols = format_universe(universe)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A 股投资研究报告</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9; --panel: #ffffff; --text: #1f2933; --muted: #667085;
      --line: #d9dee7; --accent: #1f6feb; --good: #127c56; --watch: #8a5a00;
      --neutral: #52616f; --bad: #b42318; --soft: #fbfcfe;
      --shadow: 0 10px 28px rgba(31, 41, 51, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; }}
    .wrap {{ max-width: 1160px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero, .metric, .panel, .stock-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
    .hero {{ padding: 28px; }} h1, h2, h3, h4, p {{ margin-top: 0; }}
    h1 {{ font-size: 28px; line-height: 1.25; margin-bottom: 10px; }} h2 {{ font-size: 20px; margin-bottom: 4px; }}
    h3 {{ font-size: 18px; margin-bottom: 2px; }} h4 {{ font-size: 14px; margin: 16px 0 8px; color: var(--muted); }}
    .muted, .meta, .hero p, .panel-title p, .stock-card header p {{ color: var(--muted); }}
    .meta {{ display: flex; gap: 16px; flex-wrap: wrap; margin-top: 16px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0 20px; }}
    .metric {{ padding: 16px; }} .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 16px; word-break: break-word; }}
    .panel {{ padding: 20px; margin-bottom: 20px; }} .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 840px; }}
    th, td {{ padding: 12px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 13px; font-weight: 600; background: #fafbfc; }} td span {{ color: var(--muted); font-size: 13px; }}
    .badge {{ display: inline-flex; align-items: center; min-height: 26px; padding: 3px 9px; border-radius: 999px; font-size: 13px; font-weight: 700; border: 1px solid transparent; white-space: nowrap; }}
    .rating-strong {{ color: var(--good); background: #e8f7f0; border-color: #b8e6d0; }}
    .rating-watch {{ color: var(--accent); background: #eaf2ff; border-color: #bfd6ff; }}
    .rating-observe {{ color: var(--watch); background: #fff4d6; border-color: #f3d37a; }}
    .rating-neutral {{ color: var(--neutral); background: #eef1f5; border-color: #d7dde5; }}
    .rating-avoid {{ color: var(--bad); background: #fff0ee; border-color: #f3c1bc; }}
    .cards {{ display: grid; gap: 16px; }} .stock-card {{ padding: 20px; }}
    .stock-card header {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }}
    .stock-meta {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; color: var(--muted); }}
    .stock-meta span {{ border: 1px solid var(--line); border-radius: 6px; padding: 6px 9px; background: var(--soft); }} .stock-meta strong {{ color: var(--text); }}
    .scores {{ display: grid; gap: 8px; margin: 14px 0 16px; }} .score-row {{ display: grid; grid-template-columns: 92px 1fr 44px; gap: 10px; align-items: center; }}
    .score-row span {{ color: var(--muted); font-size: 13px; }} .bar {{ height: 8px; border-radius: 999px; background: #e7ebf0; overflow: hidden; }}
    .bar i {{ display: block; height: 100%; background: var(--accent); border-radius: inherit; }}
    .metric-chips {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
    .metric-chips span {{ display: block; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: var(--soft); }}
    .metric-chips em {{ display: block; font-style: normal; color: var(--muted); font-size: 12px; }} .metric-chips strong {{ display: block; margin-top: 2px; font-size: 13px; word-break: break-word; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }} ol {{ margin: 0; padding-left: 20px; }} li {{ margin: 5px 0; }}
    .event-source {{ display: inline-block; margin-left: 6px; color: var(--muted); font-size: 13px; }}
    .event-source a {{ color: var(--accent); text-decoration: none; }}
    .event-source a:hover {{ text-decoration: underline; }}
    .disclaimer {{ margin-top: 22px; padding: 18px; border: 1px solid var(--line); border-radius: 8px; color: var(--muted); background: var(--soft); }}
    @media (max-width: 860px) {{ .metrics, .grid-2, .metric-chips {{ grid-template-columns: 1fr; }} .hero {{ padding: 22px; }} h1 {{ font-size: 24px; }} .score-row {{ grid-template-columns: 82px 1fr 38px; }} }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>A 股投资研究报告</h1>
      <p>{esc(summary.get("market_view", "未提供市场摘要。"))}</p>
      <div class="meta">
        <span>数据截止日期：{esc(payload["as_of"])}</span>
        <span>任务类型：{esc(payload["task_type"])}</span>
        <span>股票池：{esc(symbols)}</span>
      </div>
    </section>
    {metric_cards(payload)}
    {ranking_table(payload["results"])}
    {stock_cards(payload["results"])}
    <section class="disclaimer">
      <strong>合规提示</strong>
      <p>{esc(payload["compliance_disclaimer"])}</p>
      <p>本 HTML 报告仅根据同名结构化 JSON 文件生成，未额外新增未经记录的数据事实。</p>
    </section>
  </main>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: generate_html_report.py <signal.json> <report.html>")
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
    report_path.write_text(build_html(payload), encoding="utf-8")
    print(f"WROTE {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
