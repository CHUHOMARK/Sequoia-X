"""高旗形整理策略：强动量后极度收敛缩量。"""

import pandas as pd
from sequoia_x.core.logger import get_logger
from sequoia_x.strategy.base import BaseStrategy

logger = get_logger(__name__)


class HighTightFlagStrategy(BaseStrategy):
    webhook_key: str = "flag"
    _MIN_BARS: int = 40

    def run(self) -> list[str]:
        symbols = self.engine.get_local_symbols()
        selected: list[str] = []
        for symbol in symbols:
            try:
                df = self.engine.get_ohlcv(symbol)
                if len(df) < self._MIN_BARS:
                    continue
                tail40 = df.tail(40)
                tail10 = df.tail(10)
                high40 = tail40["high"].max()
                low40 = tail40["low"].min()
                high10 = tail10["high"].max()
                low10 = tail10["low"].min()
                if low40 == 0 or low10 == 0:
                    continue
                momentum = high40 / low40 > 1.6
                consolidation = high10 / low10 < 1.15
                high_level = low10 >= high40 * 0.8
                vol_ma20 = df["volume"].iloc[-21:-1].mean()
                shrink = df["volume"].iloc[-1] < vol_ma20 * 0.6
                if momentum and consolidation and high_level and shrink:
                    selected.append(symbol)
            except Exception as exc:
                logger.warning(f"[{symbol}] HighTightFlagStrategy 计算失败：{exc}")
                continue
        logger.info(f"HighTightFlagStrategy 选出 {len(selected)} 只股票")
        return selected
