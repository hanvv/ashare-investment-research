#!/usr/bin/env python3
"""Enrich factor input JSON with recent CNInfo announcement/event data.

The script fetches public announcement titles from cninfo.com.cn and converts
them into lightweight event signals for scoring. It does not invent events: if
the source is unavailable, the original missing `announcements` marker remains.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_URL = "http://static.cninfo.com.cn/"
CNINFO_STOCK_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"

POSITIVE_KEYWORDS = [
    "回购",
    "增持",
    "中标",
    "合同",
    "预增",
    "扭亏",
    "分红",
    "股权激励",
]
NEGATIVE_KEYWORDS = [
    "减持",
    "问询",
    "监管",
    "处罚",
    "立案",
    "诉讼",
    "仲裁",
    "预亏",
    "亏损",
    "更正",
    "风险提示",
    "退市",
    "债务逾期",
    "被执行",
]
HIGH_SEVERITY_KEYWORDS = ["处罚", "立案", "退市", "债务逾期", "预亏", "重大诉讼"]


def parse_as_of(payload: dict[str, Any]) -> datetime:
    raw = str(payload.get("as_of") or datetime.now().strftime("%Y-%m-%d"))
    return datetime.strptime(raw[:10], "%Y-%m-%d")


def to_code(symbol: str) -> str:
    return str(symbol).split(".")[0]


def cninfo_column(symbol: str) -> str:
    return "sse" if str(symbol).endswith(".SH") else "szse"


def remove_missing(data_quality: dict[str, Any], fields: list[str]) -> None:
    missing = list(data_quality.get("missing_fields") or [])
    data_quality["missing_fields"] = [field for field in missing if field not in fields]


def add_missing(data_quality: dict[str, Any], field: str) -> None:
    missing = list(data_quality.get("missing_fields") or [])
    if field not in missing:
        missing.append(field)
    data_quality["missing_fields"] = missing


def fetch_stock_org_map() -> dict[str, str]:
    request = Request(CNINFO_STOCK_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    mapping = {}
    for item in payload.get("stockList", []):
        if isinstance(item, dict) and item.get("code") and item.get("orgId"):
            mapping[str(item["code"]).zfill(6)] = str(item["orgId"])
    return mapping


def classify_event(title: str) -> tuple[str, str]:
    impact = "neutral"
    if any(keyword in title for keyword in POSITIVE_KEYWORDS):
        impact = "positive"
    if any(keyword in title for keyword in NEGATIVE_KEYWORDS):
        impact = "negative"
    severity = "high" if any(keyword in title for keyword in HIGH_SEVERITY_KEYWORDS) else "medium"
    return impact, severity


def apply_factor_flags(factors: dict[str, Any], title: str) -> None:
    if "预增" in title or "扭亏" in title:
        factors["positive_earnings_guidance"] = True
    if "回购" in title and ("注销" in title or "方案" in title):
        factors["large_repurchase_cancel"] = True
    if "增持" in title:
        factors["insider_increase"] = True
    if "中标" in title or "合同" in title:
        factors["major_contract"] = True
    if "减持" in title:
        factors["shareholder_reduction"] = True
    if "问询" in title or "监管" in title:
        factors["regulatory_inquiry"] = True
    if "处罚" in title or "立案" in title:
        factors["penalty"] = True
    if "预亏" in title or "亏损" in title:
        factors["negative_earnings_guidance"] = True


def event_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    title = str(row.get("announcementTitle") or "").strip()
    adjunct_url = str(row.get("adjunctUrl") or "").strip()
    if not title:
        return None
    raw_time = row.get("announcementTime")
    date = ""
    if isinstance(raw_time, (int, float)):
        date = datetime.fromtimestamp(raw_time / 1000).strftime("%Y-%m-%d")
    impact, severity = classify_event(title)
    return {
        "date": date,
        "title": title,
        "impact": impact,
        "severity": severity,
        "source": "cninfo.hisAnnouncement",
        "url": CNINFO_STATIC_URL + adjunct_url if adjunct_url else "",
    }


def fetch_announcements(
    symbol: str,
    start: datetime,
    end: datetime,
    page_size: int,
    org_map: dict[str, str],
) -> list[dict[str, Any]]:
    code = to_code(symbol)
    org_id = org_map.get(code, "")
    data = {
        "stock": f"{code},{org_id}" if org_id else code,
        "tabName": "fulltext",
        "pageSize": str(page_size),
        "pageNum": "1",
        "column": cninfo_column(symbol),
        "category": "",
        "plate": "",
        "seDate": f"{start.strftime('%Y-%m-%d')}~{end.strftime('%Y-%m-%d')}",
        "searchkey": "",
        "secid": "",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    body = urlencode(data).encode("utf-8")
    request = Request(
        CNINFO_QUERY_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    rows = payload.get("announcements") or []
    events = []
    for row in rows:
        if isinstance(row, dict):
            event = event_from_row(row)
            if event:
                events.append(event)
    return events


def enrich_one(
    stock: dict[str, Any],
    as_of: datetime,
    lookback_days: int,
    page_size: int,
    org_map: dict[str, str],
) -> dict[str, Any]:
    symbol = str(stock.get("symbol", ""))
    factors = stock.setdefault("factors", {})
    data_quality = stock.setdefault("data_quality", {"missing_fields": [], "quality_score": 0.5})
    start = as_of - timedelta(days=lookback_days)
    audit: dict[str, Any] = {"symbol": symbol, "ok": False, "events": 0, "error": ""}
    try:
        events = fetch_announcements(symbol, start, as_of, page_size, org_map)
    except Exception as exc:  # pragma: no cover - network/source dependent
        audit["error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
        add_missing(data_quality, "announcements")
        return audit

    existing = [event for event in stock.get("events", []) if isinstance(event, dict)]
    by_key = {(event.get("date"), event.get("title")): event for event in existing}
    for event in events:
        by_key[(event.get("date"), event.get("title"))] = event
        apply_factor_flags(factors, str(event.get("title", "")))
    stock["events"] = list(by_key.values())[:page_size]

    if events:
        remove_missing(data_quality, ["announcements", "events"])
        data_quality["quality_score"] = max(float(data_quality.get("quality_score", 0.5)), 0.82)
    else:
        remove_missing(data_quality, ["announcements", "events"])
        data_quality["quality_score"] = max(float(data_quality.get("quality_score", 0.5)), 0.78)

    audit.update({"ok": True, "events": len(events), "window": f"{start.date()}~{as_of.date()}"})
    return audit


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Usage: enrich_cninfo_announcements.py <input-factors.json> <output-factors.json> [--lookback-days N] [--page-size N]")
        return 2

    lookback_days = 90
    page_size = 10
    if "--lookback-days" in argv:
        lookback_days = int(argv[argv.index("--lookback-days") + 1])
    if "--page-size" in argv:
        page_size = int(argv[argv.index("--page-size") + 1])

    input_path = Path(argv[1])
    output_path = Path(argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    as_of = parse_as_of(payload)

    try:
        org_map = fetch_stock_org_map()
    except Exception as exc:  # pragma: no cover - network/source dependent
        print(f"CNInfo stock org map unavailable: {type(exc).__name__}:{str(exc)[:240]}")
        org_map = {}

    audits = []
    enriched = 0
    for stock in payload.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        audit = enrich_one(stock, as_of, lookback_days, page_size, org_map)
        audits.append(audit)
        if audit.get("ok"):
            enriched += 1
        time.sleep(0.2)

    sources = list(payload.get("data_sources") or [])
    if "cninfo.hisAnnouncement" not in sources:
        sources.append("cninfo.hisAnnouncement")
    payload["data_sources"] = sources
    payload["market_view"] = (
        f"{payload.get('market_view', '')} 已尝试使用巨潮资讯补充近 {lookback_days} 天公告/事件数据；"
        f"成功覆盖 {enriched} 只股票。"
    ).strip()
    payload["announcement_enrichment"] = {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "source": "cninfo.hisAnnouncement",
        "lookback_days": lookback_days,
        "page_size": page_size,
        "org_map_size": len(org_map),
        "enriched": enriched,
        "audits": audits,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {output_path}")
    print(f"announcement enriched: {enriched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
