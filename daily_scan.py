#!/usr/bin/env python3
"""
Sequoia-X 每日扫描脚本 (daily_scan.py)
数据来源：akshare stock_zh_a_daily（新浪财经，无需 TickFlow API Key）
功能：
  1. 拉取深市 A 股股票列表（深交所官方接口）
  2. 下载近 90 个自然日行情并写入本地 SQLite
  3. 依次执行所有内置策略，输出选股结果
  4. 生成 Markdown 格式日报并保存至 reports/daily_report_YYYYMMDD.md
"""
import sqlite3
import sys
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import Counter

import pandas as pd

# ── 路径设置 ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)

# ── 依赖检查 ──────────────────────────────────────────────────────────────────
try:
    import akshare as ak
except ImportError:
    print("[ERROR] akshare 未安装，请执行：pip install akshare")
    sys.exit(1)

# ── 常量 ──────────────────────────────────────────────────────────────────────
DB_PATH = PROJECT_DIR / "data" / "sequoia_v2.db"
REPORT_DIR = PROJECT_DIR / "reports"
TODAY = date.today().strftime("%Y-%m-%d")
TODAY_COMPACT = TODAY.replace("-", "")
START_DATE = (date.today() - timedelta(days=90)).strftime("%Y%m%d")
MAX_STOCKS = 150            # 扫描股票数量（每只约 2s，150 只约 5 分钟）

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ── 数据库初始化 ───────────────────────────────────────────────────────────────
def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_daily (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol   TEXT    NOT NULL,
                date     TEXT    NOT NULL,
                open     REAL, high REAL, low REAL, close REAL,
                volume   REAL, turnover REAL,
                UNIQUE (symbol, date)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_symbol_date ON stock_daily (symbol, date);")
        conn.commit()
    log(f"数据库初始化完成：{DB_PATH}")

# ── 股票代码转换 ──────────────────────────────────────────────────────────────
def to_akshare_symbol(code: str) -> str:
    """将6位股票代码转换为 akshare stock_zh_a_daily 所需格式（如 sz000001 / sh600000）"""
    if code.startswith(("6", "9")):
        return f"sh{code}"
    elif code.startswith(("4", "8")):
        return f"bj{code}"
    else:
        return f"sz{code}"

# ── 获取 A 股股票列表 ─────────────────────────────────────────────────────────
def get_stock_list() -> list[str]:
    log("正在获取 A 股股票列表（深市）...")
    try:
        df_sz = ak.stock_info_sz_name_code(symbol="A股列表")
        # 过滤 ST、退市
        mask = ~df_sz["A股简称"].str.contains("ST|退", na=False)
        sz_codes = df_sz.loc[mask, "A股代码"].astype(str).str.zfill(6).tolist()
        log(f"深市 A 股：{len(sz_codes)} 只（已过滤 ST/退市）")
    except Exception as e:
        log(f"获取深市股票列表失败：{e}")
        sz_codes = []

    # 补充沪市蓝筹股（确保策略有代表性数据）
    sh_blue_chips = [
        "600000", "600016", "600019", "600028", "600030", "600036",
        "600048", "600050", "600104", "600196", "600276", "600309",
        "600519", "600570", "600585", "600600", "600690", "600703",
        "600741", "600809", "600887", "600900", "601012", "601066",
        "601088", "601111", "601166", "601211", "601288", "601318",
        "601328", "601336", "601398", "601601", "601628", "601668",
        "601688", "601766", "601818", "601857", "601888", "601899",
        "601919", "601939", "601988", "601989", "603259", "603288",
        "603501", "603986",
    ]
    all_codes = sz_codes + sh_blue_chips
    # 去重
    seen = set()
    result = []
    for c in all_codes:
        if c not in seen:
            seen.add(c)
            result.append(c)

    log(f"合计 {len(result)} 只股票，取前 {MAX_STOCKS} 只进行扫描")
    return result[:MAX_STOCKS]

# ── 下载单只股票行情 ──────────────────────────────────────────────────────────
def fetch_and_store(code: str) -> int:
    """下载 code 的日 K 数据并写入 SQLite，返回写入行数。"""
    try:
        ak_sym = to_akshare_symbol(code)
        df = ak.stock_zh_a_daily(
            symbol=ak_sym,
            start_date=START_DATE,
            end_date=TODAY_COMPACT,
            adjust="hfq",
        )
        if df is None or df.empty:
            return 0
        # 标准化列名
        df = df.rename(columns={
            "date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "amount": "turnover",
        })
        df["symbol"] = code
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        cols = ["symbol", "date", "open", "high", "low", "close", "volume", "turnover"]
        for col in cols:
            if col not in df.columns:
                df[col] = 0.0
        df = df[cols].dropna(subset=["close"])
        df = df[df["volume"] > 0]
        if df.empty:
            return 0
        with sqlite3.connect(DB_PATH) as conn:
            for d in df["date"].unique():
                conn.execute("DELETE FROM stock_daily WHERE symbol=? AND date=?", (code, d))
            df.to_sql("stock_daily", conn, if_exists="append", index=False, method="multi", chunksize=200)
            conn.commit()
        return len(df)
    except Exception:
        return 0

# ── 批量同步行情 ──────────────────────────────────────────────────────────────
def sync_market_data(symbols: list[str]) -> int:
    log(f"正在同步行情数据（{START_DATE} ~ {TODAY_COMPACT}），共 {len(symbols)} 只股票...")
    total = 0
    failed = 0
    for i, sym in enumerate(symbols):
        n = fetch_and_store(sym)
        if n > 0:
            total += n
        else:
            failed += 1
        if (i + 1) % 30 == 0:
            log(f"  已处理 {i+1}/{len(symbols)} 只，累计写入 {total} 条，失败 {failed} 只")
    log(f"行情同步完成：写入 {total} 条记录，{failed} 只获取失败")
    return total

# ── 策略执行 ──────────────────────────────────────────────────────────────────
def run_strategies() -> dict[str, list[str]]:
    from sequoia_x.core.config import Settings
    from sequoia_x.data.engine import DataEngine
    from sequoia_x.strategy.ma_volume import MaVolumeStrategy
    from sequoia_x.strategy.turtle_trade import TurtleTradeStrategy
    from sequoia_x.strategy.high_tight_flag import HighTightFlagStrategy
    from sequoia_x.strategy.limit_up_shakeout import LimitUpShakeoutStrategy
    from sequoia_x.strategy.uptrend_limit_down import UptrendLimitDownStrategy
    from sequoia_x.strategy.rps_breakout import RpsBreakoutStrategy
    from sequoia_x.strategy.private_placement import PrivatePlacementStrategy
    from sequoia_x.strategy.n_shape import NShapeStrategy

    settings = Settings(
        tickflow_api_key="dummy_not_needed",
        db_path=str(DB_PATH),
        start_date="2024-01-01",
    )
    engine = DataEngine.__new__(DataEngine)
    engine.db_path = str(DB_PATH)
    engine.start_date = settings.start_date
    engine.tickflow_api_key = settings.tickflow_api_key
    engine._tf = None

    strategy_classes = [
        ("均线放量", MaVolumeStrategy),
        ("海龟突破", TurtleTradeStrategy),
        ("高窄旗形", HighTightFlagStrategy),
        ("涨停洗盘", LimitUpShakeoutStrategy),
        ("上升跌停", UptrendLimitDownStrategy),
        ("RPS突破", RpsBreakoutStrategy),
        ("定增预期", PrivatePlacementStrategy),
        ("N字形态", NShapeStrategy),
    ]

    results: dict[str, list[str]] = {}
    for name, cls in strategy_classes:
        log(f"执行策略：{name}")
        try:
            strategy = cls(engine=engine, settings=settings)
            selected = strategy.run()
            results[name] = selected
            log(f"  → 选出 {len(selected)} 只股票")
        except Exception as e:
            log(f"  策略执行失败：{e}")
            results[name] = []
    return results

# ── 生成日报 ──────────────────────────────────────────────────────────────────
def generate_report(results: dict[str, list[str]], total_synced: int, symbols_count: int) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"daily_report_{TODAY_COMPACT}.md"

    counter = Counter()
    for symbols in results.values():
        for s in symbols:
            counter[s] += 1

    lines = [
        f"# Sequoia-X 每日选股报告",
        f"",
        f"**日期：** {TODAY}  ",
        f"**扫描股票数：** {symbols_count}  ",
        f"**行情记录写入：** {total_synced} 条  ",
        f"**生成时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"---",
        f"",
        f"## 策略选股汇总",
        f"",
        f"| 策略名称 | 选股数量 | 代表标的（前10只）|",
        f"|----------|----------|------------------|",
    ]

    for name, symbols in results.items():
        sym_str = "、".join(symbols[:10]) + ("..." if len(symbols) > 10 else "") if symbols else "无"
        lines.append(f"| {name} | {len(symbols)} | {sym_str} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 多策略共振标的",
        f"",
    ]

    multi_hit = [(s, c) for s, c in counter.most_common() if c >= 2]
    if multi_hit:
        lines.append(f"| 股票代码 | 命中策略数 |")
        lines.append(f"|----------|------------|")
        for s, c in multi_hit:
            lines.append(f"| {s} | {c} |")
    else:
        lines.append("本次扫描暂无多策略共振标的。")

    lines += [
        f"",
        f"---",
        f"",
        f"## 各策略详细选股",
        f"",
    ]

    for name, symbols in results.items():
        lines.append(f"### {name}")
        lines.append(f"")
        if symbols:
            lines.append("、".join(symbols))
        else:
            lines.append("本次无选股结果。")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"*由 Sequoia-X V2 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path

# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    log("=" * 60)
    log(f"  Sequoia-X 每日扫描启动  |  {TODAY}")
    log("=" * 60)

    init_db()

    symbols = get_stock_list()
    if not symbols:
        log("股票列表为空，退出")
        sys.exit(1)

    total_synced = sync_market_data(symbols)

    log("")
    log("─" * 60)
    log("  开始执行策略扫描")
    log("─" * 60)
    results = run_strategies()

    log("")
    report_path = generate_report(results, total_synced, len(symbols))
    log(f"日报已保存至：{report_path}")

    log("")
    log("=" * 60)
    log("  扫描完成 — 结果摘要")
    log("=" * 60)
    total_candidates = sum(len(v) for v in results.values())
    log(f"共执行 {len(results)} 个策略，合计选出 {total_candidates} 只（含重复）股票")
    for name, syms in results.items():
        status = f"{len(syms)} 只" if syms else "无"
        log(f"  {name}: {status}")

    return report_path

if __name__ == "__main__":
    main()
