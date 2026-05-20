"""A 股实时快讯模块 —— 数据来源 https://hhxg.top 静态 JSON API。"""
from __future__ import annotations
import json
from sequoia_x.modules._common import fetch_json, check_schema, print_cache_hint

def fetch():
    data, from_cache = fetch_json("news/news.json", "news.json")
    check_schema(data)
    date_str = data.get("meta", {}).get("date", "unknown")
    print_cache_hint(from_cache, date_str)
    return data

def fmt_news(data, limit=20):
    news_list = data if isinstance(data, list) else data.get("news", [])
    if not news_list: return "## 实时快讯\n\n暂无数据"
    lines = ["## 实时快讯", ""]
    for item in news_list[:limit]:
        time_str = item.get("time", "")
        title = item.get("title", "-")
        source = item.get("source", "")
        prefix = f"[{source}] " if source else ""
        lines.append(f"- {time_str} {prefix}{title}")
    return "\n".join(lines)

def run(limit=20, use_json=False):
    data = fetch()
    if use_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(fmt_news(data, limit))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="实时快讯")
    parser.add_argument("-n", "--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", dest="use_json")
    args = parser.parse_args()
    run(limit=args.limit, use_json=args.use_json)
