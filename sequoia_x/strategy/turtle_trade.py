"""海龟交易策略：20日新高突破 + 成交额过亿 + 动量阳线过滤。"""

import pandas as pd
from sequoia_x.core.logger import get_logger
from sequoia_x.strategy.base import BaseStrategy

logger = get_logger(__name__)


class TurtleTradeStrategy(BaseStrategy):
    """海龟交易策略（A股防诱多改良版）。"""
    webhook_key: str = "turtle"
    _MIN_BARS: int = 21

    def _get_market_caps(self, symbols: list[str]) -> dict[str, float]:
        from tickflow import TickFlow
        tf = TickFlow(api_key=self.engine.tickflow_api_key)
        market_caps: dict[str, float] = {}
        def to_tf_symbol(code: str) -> str:
            suffix = "SH" if code.startswith(("6", "9")) else "SZ"
            return f"{code}.{suffix}"
        tf_symbols = [to_tf_symbol(s) for s in symbols]
        try:
            quotes = tf.quotes.get(symbols=tf_symbols, as_dataframe=True)
            if quotes is not None and not quotes.empty:
                for _, row in quotes.iterrows():
                    symbol = row['symbol'].split('.')[0]
                    market_cap = row.get('market_cap', 0) or row.get('circulating_market_cap', 0)
                    if market_cap > 0:
                        market_caps[symbol] = market_cap
        except Exception as e:
            logger.warning(f"获取流通市值失败: {e}")
        return market_caps

    def run(self) -> list[str]:
        symbols = self.engine.get_local_symbols()
        candidates: list[str] = []
        for symbol in symbols:
            try:
                df = self.engine.get_ohlcv(symbol)
                if len(df) < self._MIN_BARS:
                    continue
                df["high_20"] = df["high"].shift(1).rolling(20).max()
                last = df.iloc[-1]
                prev = df.iloc[-2]
                if pd.isna(last["high_20"]):
                    continue
                breakout = last["close"] > last["high_20"]
                liquid = last["turnover"] > 100_000_000
                is_yang = last["close"] > last["open"]
                is_up = last["close"] > prev["close"]
                if breakout and liquid and is_yang and is_up:
                    candidates.append(symbol)
            except Exception as exc:
                logger.warning(f"[{symbol}] TurtleTradeStrategy 计算失败：{exc}")
                continue
        if candidates:
            market_caps = self._get_market_caps(candidates)
            candidates.sort(key=lambda s: market_caps.get(s, 0), reverse=True)
        logger.info(f"TurtleTradeStrategy 选出 {len(candidates)} 只股票")
        return candidates
