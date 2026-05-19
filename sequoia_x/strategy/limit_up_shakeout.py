"""涨停洗盘策略：昨日涨停后今日放量收阴但不破昨收。"""

import pandas as pd
from sequoia_x.core.logger import get_logger
from sequoia_x.strategy.base import BaseStrategy

logger = get_logger(__name__)


class LimitUpShakeoutStrategy(BaseStrategy):
    webhook_key: str = "shakeout"
    _MIN_BARS: int = 3

    def run(self) -> list[str]:
        symbols = self.engine.get_local_symbols()
        selected: list[str] = []
        for symbol in symbols:
            try:
                df = self.engine.get_ohlcv(symbol)
                if len(df) < self._MIN_BARS:
                    continue
                prev2 = df.iloc[-3]
                prev1 = df.iloc[-2]
                today = df.iloc[-1]
                limit_up_yesterday = prev1["close"] >= prev2["close"] * 1.095
                bearish_today = today["close"] < today["open"]
                volume_surge = today["volume"] > prev1["volume"] * 2.0
                support_hold = today["low"] >= prev1["close"]
                if limit_up_yesterday and bearish_today and volume_surge and support_hold:
                    selected.append(symbol)
            except Exception as exc:
                logger.warning(f"[{symbol}] LimitUpShakeoutStrategy 计算失败：{exc}")
                continue
        logger.info(f"LimitUpShakeoutStrategy 选出 {len(selected)} 只股票")
        return selected
