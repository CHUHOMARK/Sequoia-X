"""数据引擎模块：负责 SQLite 行情数据存储与 TickFlow 增量同步。"""

import sqlite3
from pathlib import Path
from datetime import date, timedelta
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import pandas as pd
from sequoia_x.core.config import Settings
from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_daily (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol   TEXT    NOT NULL,
    date     TEXT    NOT NULL,
    open     REAL, high     REAL, low      REAL, close    REAL,
    volume   REAL, turnover REAL,
    UNIQUE (symbol, date)
);
"""
_CREATE_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_symbol_date ON stock_daily (symbol, date);"

BATCH_SIZE = 200
BATCH_RPM = 120
SINGLE_RPM = 300
BATCH_INTERVAL = 60.0 / BATCH_RPM
SINGLE_INTERVAL = 60.0 / SINGLE_RPM
BATCH_CONCURRENCY = 5


def _to_tickflow_symbol(code: str) -> str:
    suffix = "SH" if code.startswith(("6", "9")) else "SZ"
    return f"{code}.{suffix}"


class _RateLimiter:
    def __init__(self, min_interval: float):
        self._lock = threading.Lock()
        self._min_interval = min_interval
        self._last_time: float = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_time = time.monotonic()


class DataEngine:
    def __init__(self, settings: Settings) -> None:
        self.db_path: str = settings.db_path
        self.start_date: str = settings.start_date
        self.tickflow_api_key: str = settings.tickflow_api_key
        self._tf = None
        self._init_db()

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
            conn.commit()
        logger.info(f"数据库初始化完成：{self.db_path}")

    def _get_tickflow_client(self):
        if self._tf is None:
            from tickflow import TickFlow
            self._tf = TickFlow(api_key=self.tickflow_api_key)
        return self._tf

    def _get_last_date(self, symbol: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT MAX(date) FROM stock_daily WHERE symbol = ?", (symbol,)).fetchone()
        return row[0] if row and row[0] else None

    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql("SELECT * FROM stock_daily WHERE symbol = ? ORDER BY date", conn, params=(symbol,))
        return df

    def _fetch_batch(self, tf, tf_symbols: list[str], count: int) -> dict:
        for attempt in range(3):
            try:
                return tf.klines.batch(tf_symbols, period="1d", count=count, adjust="forward", as_dataframe=True)
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                else:
                    logger.error(f"批量请求最终失败: {e}")
                    return {}

    def _process_batch_results(self, batch_symbols, tf_symbols, dfs) -> list[list]:
        rows = []
        for orig_symbol, tf_symbol in zip(batch_symbols, tf_symbols):
            if tf_symbol not in dfs: continue
            df = dfs[tf_symbol]
            if df.empty: continue
            last_date = self._get_last_date(orig_symbol)
            if last_date: df = df[df["trade_date"] > last_date]
            if df.empty: continue
            for _, r in df.iterrows():
                rows.append([orig_symbol, r["trade_date"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["amount"]])
        return rows

    def sync_today_bulk(self) -> int:
        tf = self._get_tickflow_client()
        today_str = date.today().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT symbol, MAX(date) FROM stock_daily GROUP BY symbol").fetchall()
        if not rows: return 0
        symbols_to_update = [s for s, d in rows if not (d and d >= today_str)]
        if not symbols_to_update: return 0
        batches = []
        total_batches = (len(symbols_to_update) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(total_batches):
            start = i * BATCH_SIZE
            end = min(start + BATCH_SIZE, len(symbols_to_update))
            batch = symbols_to_update[start:end]
            tf_batch = [_to_tickflow_symbol(s) for s in batch]
            batches.append((i, batch, tf_batch))
        rate_limiter = _RateLimiter(BATCH_INTERVAL)
        all_rows, completed, lock = [], 0, threading.Lock()
        def _worker(batch_idx, batch_syms, tf_syms):
            nonlocal completed
            rate_limiter.wait()
            dfs = self._fetch_batch(tf, tf_syms, count=30)
            if dfs:
                new_rows = self._process_batch_results(batch_syms, tf_syms, dfs)
                with lock: all_rows.extend(new_rows); completed += 1
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=BATCH_CONCURRENCY) as pool:
            futures = [pool.submit(_worker, idx, syms, tf_syms) for idx, syms, tf_syms in batches]
            for f in as_completed(futures): f.result()
        elapsed = time.time() - start_time
        if not all_rows: return 0
        df = pd.DataFrame(all_rows, columns=["symbol", "date", "open", "high", "low", "close", "volume", "turnover"])
        for col in ["open", "high", "low", "close", "volume", "turnover"]: df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close"])
        df = df[df["volume"] > 0]
        count = len(df)
        with sqlite3.connect(self.db_path) as conn:
            for d in df["date"].unique().tolist(): conn.execute("DELETE FROM stock_daily WHERE date = ?", (d,))
            df.to_sql("stock_daily", conn, if_exists="append", index=False, method="multi", chunksize=500)
            conn.commit()
        return count

    def backfill(self, symbols: list[str]) -> None:
        tf = self._get_tickflow_client()
        today_str = date.today().strftime("%Y-%m-%d")
        symbols_to_fetch = [s for s in symbols if not (self._get_last_date(s) and self._get_last_date(s) >= today_str)]
        if not symbols_to_fetch: return
        success, skipped, failed, lock = 0, 0, 0, threading.Lock()
        batches = []
        total_batches = (len(symbols_to_fetch) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(total_batches):
            start = i * BATCH_SIZE
            end = min(start + BATCH_SIZE, len(symbols_to_fetch))
            batch = symbols_to_fetch[start:end]
            tf_batch = [_to_tickflow_symbol(s) for s in batch]
            batches.append((i, batch, tf_batch))
        rate_limiter = _RateLimiter(BATCH_INTERVAL)
        start_time, completed = time.time(), 0
        def _worker(batch_idx, batch_syms, tf_syms):
            nonlocal success, skipped, failed, completed
            rate_limiter.wait()
            dfs = self._fetch_batch(tf, tf_syms, count=500)
            if not dfs:
                with lock: failed += len(tf_syms); completed += 1
                return
            for orig_symbol, tf_symbol in zip(batch_syms, tf_syms):
                if tf_symbol not in dfs: skipped += 1; continue
                df = dfs[tf_symbol]
                if df.empty: skipped += 1; continue
                last_date = self._get_last_date(orig_symbol)
                if last_date: df = df[df["trade_date"] > last_date]
                if df.empty: skipped += 1; continue
                df_out = pd.DataFrame({"symbol": orig_symbol, "date": df["trade_date"].values, "open": df["open"].values, "high": df["high"].values, "low": df["low"].values, "close": df["close"].values, "volume": df["volume"].values, "turnover": df["amount"].values})
                for col in ["open", "high", "low", "close", "volume", "turnover"]: df_out[col] = pd.to_numeric(df_out[col], errors="coerce")
                df_out = df_out.dropna(subset=["close"])
                df_out = df_out[df_out["volume"] > 0]
                if df_out.empty: skipped += 1; continue
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        df_out.to_sql("stock_daily", conn, if_exists="append", index=False, method="multi", chunksize=500)
                    success += 1
                except sqlite3.IntegrityError: skipped += 1
            with lock: completed += 1
        with ThreadPoolExecutor(max_workers=BATCH_CONCURRENCY) as pool:
            futures = [pool.submit(_worker, idx, syms, tf_syms) for idx, syms, tf_syms in batches]
            for f in as_completed(futures): f.result()
        elapsed = time.time() - start_time
        logger.info(f"回填完成 — 成功: {success} | 跳过: {skipped} | 失败: {failed}，总耗时 {elapsed:.1f}s")

    def get_all_symbols(self) -> list[str]:
        tf = self._get_tickflow_client()
        for attempt in range(3):
            try:
                universe = tf.universes.get("CN_Equity_A")
                symbols = [s.split(".")[0] for s in universe["symbols"]]
                logger.info(f"获取股票列表完成，共 {len(symbols)} 只")
                return symbols
            except Exception as e:
                if attempt < 2: time.sleep(2 ** (attempt + 1))
                else: logger.error(f"获取股票列表失败: {e}"); return []

    def get_local_symbols(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT DISTINCT symbol FROM stock_daily").fetchall()
        return [row[0] for row in rows]
