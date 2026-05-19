"""上升趋势跌停策略：趋势中放量跌停，捕捉错杀机会。"""

import pandas as pd
from sequoia_x.core.logger import get_logger
from sequoia_x.strategy.base import BaseStrategy

logger = get_logger(__name__)


class UptrendLimitDownStrategy(BaseStrategy):
    webhook_key: str = "limit_down"
    _MIN_BARS: int = 60

    def run(self) -> list[str]:
        symbols = self.engine.get_local_symbols()
        selected: list[str] = []
        for symbol in symbols:
            try:
                df = self.engine.get_ohlcv(symbol)
                if len(df) < self._MIN_BARS:
                    continue
                df["ma20"] = df["close"].rolling(20).mean()
                df["ma60"] = df["close"].rolling(60).mean()
                df["vol_ma20"] = df["volume"].rolling(20).mean()
                prev = df.iloc[-2]
                today = df.iloc[-1]
                if pd.isna(prev["ma20"]) or pd.isna(prev["ma60"]) or pd.isna(today["vol_ma20"]):
                    continue
                uptrend = prev["ma20"] > prev["ma60"]
                limit_down = today["close"] <= prev["close"] * 0.905
                volume_surge = today["volume"] > today["vol_ma20"] * 2.0
                if uptrend and limit_down and volume_surge:
                    selected.append(symbol)
            except Exception as exc:
                logger.warning(f"[{symbol}] UptrendLimitDownStrategy 计算失败：{exc}")
                continue
        logger.info(f"UptrendLimitDownStrategy 选出 {len(selected)} 只股票")
        return selected
