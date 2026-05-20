"""A 股融资融券模块 —— 数据来源 https://hhxg.top 静态 JSON API。"""
from __future__ import annotations
import json
from sequoia_x.modules._common import fetch_json, check_schema, print_cache_hint

def fetch():
    data, from_cache = fetch_json("margin/margin.json", "margin.json")
    check_schema(data)
    date_str = data.get("meta", {}).get("date", "unknown")
    print_cache_hint(from_cache, date_str)
    return data

def fmt_margin(data):
    summary = data.get("summary", {})
    if not summary: return "## 融资融券\n\n暂无数据"
    lines = ["## 融资融券", ""]
    for key, val in summary.items():
        lines.append(f"**{key}**: {val}")
    return "\n".join(lines)

def run(section="all", use_json=False):
    data = fetch()
    if use_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(fmt_margin(data))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="融资融券数据")
    parser.add_argument("--json", action="store_true", dest="use_json")
    args = parser.parse_args()
    run(use_json=args.use_json)
