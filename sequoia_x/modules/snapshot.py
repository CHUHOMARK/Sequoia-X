"""A 股日报快照模块 —— 数据来源 https://hhxg.top 静态 JSON API。"""
from __future__ import annotations
import json
from sequoia_x.modules._common import fetch_json, check_schema, print_cache_hint

def fetch():
    data, from_cache = fetch_json("assistant/skill_snapshot.json", "snapshot.json")
    check_schema(data)
    print_cache_hint(from_cache, data.get("meta", {}).get("date", "unknown"))
    return data

def _pct(val):
    if val is None: return "-"
    return f"{'+' if val > 0 else ''}{val:.2f}%"

def _amount(val):
    if val is None: return "-"
    return f"{val:.2f}亿"

def fmt_snapshot(data, sections=None):
    if sections is None:
        sections = ["ai_summary", "market", "themes", "ladder", "hotmoney", "sectors", "news", "signals", "comparison", "footer"]
    dispatch = {
        "market": lambda d: "## 市场赚钱效应\n" + str(d.get("market", {})),
        "themes": lambda d: "## 热门题材\n" + json.dumps(d.get("themes", [])[:20], ensure_ascii=False, indent=2),
        "ladder": lambda d: "## 连板天梯\n" + json.dumps(d.get("ladder", {}), ensure_ascii=False, indent=2),
        "hotmoney": lambda d: "## 游资龙虎榜\n" + json.dumps(d.get("hotmoney", {}), ensure_ascii=False, indent=2),
        "sectors": lambda d: "## 行业资金流向\n" + json.dumps(d.get("sectors", {}), ensure_ascii=False, indent=2),
        "news": lambda d: "## 宏观新闻\n" + json.dumps(d.get("news", [])[:15], ensure_ascii=False, indent=2),
        "ai_summary": lambda d: "## AI 总结\n" + json.dumps(d.get("ai_summary", {}), ensure_ascii=False, indent=2),
    }
    parts = [dispatch.get(s, lambda d: "")(data) for s in sections if s in dispatch]
    return "\n\n".join(parts)

def run(section="all", use_json=False):
    data = fetch()
    if use_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(fmt_snapshot(data))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="A 股日报快照")
    parser.add_argument("-s", "--section", default="all")
    parser.add_argument("--json", action="store_true", dest="use_json")
    args = parser.parse_args()
    run(section=args.section, use_json=args.use_json)
