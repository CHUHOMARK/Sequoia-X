"""A 股日历模块 —— 数据来源 https://hhxg.top 静态 JSON API。"""
from __future__ import annotations
import json, sys
from datetime import date, datetime, timedelta
from sequoia_x.modules._common import fetch_json, check_schema, print_cache_hint

def _fetch_trading_days(year=None):
    if year is None: year = date.today().year
    data, from_cache = fetch_json(f"calendar/trading_days_{year}.json", f"trading_days_{year}.json")
    if isinstance(data, dict): check_schema(data)
    print_cache_hint(from_cache, str(year))
    return data

def _fetch_events(kind, month=None):
    if month is None:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    data, from_cache = fetch_json(f"calendar/{kind}_{month}.json", f"{kind}_{month}.json")
    check_schema(data)
    print_cache_hint(from_cache, data.get("meta", {}).get("date", month))
    return data

def _parse_date(d):
    if isinstance(d, date): return d
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try: return datetime.strptime(str(d), fmt).date()
        except (ValueError, TypeError): continue
    return None

def _weekday_name(d):
    return ["周一","周二","周三","周四","周五","周六","周日"][d.weekday()]

def fmt_trading(data, query_date=None):
    if isinstance(data, list): days = data
    else: days = data.get("trading_days", [])
    if not days: return "## 交易日查询\n\n暂无数据"
    parsed_days = sorted([d for d in (_parse_date(d) for d in days) if d])
    if query_date is None: query_date = date.today()
    lines = ["## 交易日查询", "", f"{query_date} ({_weekday_name(query_date)}) {'是交易日' if query_date in parsed_days else '非交易日'}"]
    next_trading = next((d for d in parsed_days if d > query_date), None)
    if next_trading:
        lines.append(f"下一个交易日: {next_trading} ({_weekday_name(next_trading)})，{(next_trading - query_date).days} 天后")
    lines.append("", "本周交易日:")
    week_start = query_date - timedelta(days=query_date.weekday())
    week_end = week_start + timedelta(days=4)
    week_trading = [d for d in parsed_days if week_start <= d <= week_end]
    lines.extend([f"  - {d} ({_weekday_name(d)})" for d in week_trading] if week_trading else ["  - 本周无交易日"])
    return "\n".join(lines)

def fmt_events(data, kind_label="事件"):
    events = data.get("events", [])
    if not events: return f"## {kind_label}日历\n\n暂无数据"
    lines = [f"## {kind_label}日历", "", "| 日期 | 标签 | 描述 | 相关公司 |", "|------|------|------|----------|"]
    for ev in events[:30]:
        lines.append(f"| {ev.get('date','-')} | {ev.get('tag','')} | {ev.get('desc','-')} | {', '.join(ev.get('companies',[]))} |")
    return "\n".join(lines)

def fmt_week(trading_data=None, delivery_data=None, earnings_data=None, unlock_data=None):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    lines = [f"## 本周日历 ({week_start} ~ {week_end})", ""]
    if trading_data is None:
        try: trading_data = _fetch_trading_days(today.year)
        except Exception: trading_data = None
    if trading_data:
        days = trading_data if isinstance(trading_data, list) else trading_data.get("trading_days", [])
        parsed_days = sorted([d for d in (_parse_date(d) for d in days) if d])
        week_trading = [d for d in parsed_days if week_start <= d <= week_end]
        lines.append("### 交易日", "")
        lines.extend([f"- {d} ({_weekday_name(d)})" for d in week_trading] if week_trading else ["- 本周无交易日"])
        lines.append("")
    for kind, label, existing_data in [("earnings","财报",earnings_data),("unlock","解禁",unlock_data),("delivery","交割",delivery_data)]:
        if existing_data is None:
            try: existing_data = _fetch_events(kind, f"{today.year}-{today.month:02d}")
            except Exception: continue
        events = existing_data.get("events", [])
        week_events = [ev for ev in events if _parse_date(ev.get("date","")) and week_start <= _parse_date(ev.get("date","")) <= week_end]
        if week_events:
            lines.append(f"### {label}", "")
            for ev in week_events[:10]:
                tag = f"[{ev.get('tag','')}] " if ev.get('tag') else ""
                comp = f" ({', '.join(ev.get('companies',[]))})" if ev.get('companies') else ""
                lines.append(f"- {ev.get('date','-')} {tag}{ev.get('desc','-')}{comp}")
            lines.append("")
    return "\n".join(lines)

def run(section="week", args=None, use_json=False):
    if args is None: args = []
    if section == "week":
        trading_data = delivery_data = earnings_data = unlock_data = None
        try: trading_data = _fetch_trading_days()
        except Exception: pass
        today = date.today()
        month_str = f"{today.year}-{today.month:02d}"
        for kind in ("delivery","earnings","unlock"):
            try:
                d, _ = _fetch_events(kind, month_str)
                if kind=="delivery": delivery_data=d
                elif kind=="earnings": earnings_data=d
                elif kind=="unlock": unlock_data=d
            except Exception: pass
        if use_json:
            result = {}
            if trading_data: result["trading_days"] = trading_data
            if delivery_data: result["delivery"] = delivery_data
            if earnings_data: result["earnings"] = earnings_data
            if unlock_data: result["unlock"] = unlock_data
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else: print(fmt_week(trading_data, delivery_data, earnings_data, unlock_data))
        return
    if section == "trading":
        data = _fetch_trading_days()
        if use_json: print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            q = args[0] if args else None
            print(fmt_trading(data, _parse_date(q) if q else None))
        return
    kind_map = {"delivery":"交割","earnings":"财报","unlock":"解禁"}
    data = _fetch_events(section, args[0] if args else None)
    if use_json: print(json.dumps(data, ensure_ascii=False, indent=2))
    else: print(fmt_events(data, kind_map.get(section, section)))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="A 股日历")
    parser.add_argument("-s", "--section", default="week")
    parser.add_argument("args", nargs="*")
    parser.add_argument("--json", action="store_true", dest="use_json")
    args = parser.parse_args()
    run(section=args.section, args=args.args, use_json=args.use_json)
