"""恢恢量化数据共用工具：HTTP 请求 + 本地缓存 + schema 检查。"""
from __future__ import annotations
import json, os, sys, time, urllib.error, urllib.request
BASE_URL = "https://hhxg.top/static/data"
CACHE_DIR = os.path.expanduser("~/.cache/hhxg-market")
SUPPORTED_SCHEMA = 3
HEADERS = {"User-Agent": "sequoia-x/1.0", "X-Skill-Client": "sequoia-x"}

def fetch_json(path, cache_name=None):
    url = f"{BASE_URL}/{path}"
    cache_file = os.path.join(CACHE_DIR, cache_name) if cache_name else None
    last_err = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if cache_file: _save_cache(cache_file, data)
            return data, False
        except urllib.error.HTTPError as e:
            if e.code == 404: raise RuntimeError("数据接口不存在 (404)")
            raise RuntimeError(f"服务端错误 HTTP {e.code}")
        except json.JSONDecodeError: raise RuntimeError("数据格式异常")
        except urllib.error.URLError as e:
            last_err = e
            if attempt == 0: time.sleep(1)
    if cache_file:
        cached = _load_cache(cache_file)
        if cached: return cached, True
    raise RuntimeError("网络不可用，且无本地缓存")

def check_schema(data):
    meta = data.get("meta", {})
    ver = meta.get("schema_version", SUPPORTED_SCHEMA)
    if ver > SUPPORTED_SCHEMA:
        print(f"WARNING: 数据格式已更新 (v{ver})", file=sys.stderr)

def print_cache_hint(from_cache, date_str):
    if from_cache:
        print(f"NOTE: 使用本地缓存数据（{date_str}）", file=sys.stderr)

def _save_cache(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)
    except OSError: pass

def _load_cache(path):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except (OSError, json.JSONDecodeError): return None
