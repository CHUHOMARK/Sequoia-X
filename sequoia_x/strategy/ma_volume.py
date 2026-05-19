"""均线+成交量选股策略：5日均线上穿20日均线且成交量放大。"""

import pandas as pd
from sequoia_x.core.logger import get_logger
from sequoia_x.strategy.base import BaseStrategy

logger = get_logger(__name__)


class MaVolumeStrategy(BaseStrategy):
    webhook_key: str = "ma_volume"

    def run(self) -> list[str]:
        symbols = self.engine.get_local_symbols()
        selected: list[str] = []
        for symbol in symbols:
            try:
                df = self.engine.get_ohlcv(symbol)
                if len(df) < 20:
                    continue
                df["ma5"] = df["close"].rolling(5).mean()
                df["ma20"] = df["close"].rolling(20).mean()
                df["vol_ma20"] = df["volume"].rolling(20).mean()
                last = df.iloc[-1]
                prev = df.iloc[-2]
                golden_cross = prev["ma5"] < prev["ma20"] and last["ma5"] > last["ma20"]
                volume_surge = last["volume"] > last["vol_ma20"] * 1.5
                if golden_cross and volume_surge:
                    selected.append(symbol)
            except Exception as exc:
                logger.warning(f"[{symbol}] 策略计算失败：{exc}")
                continue
        logger.info(f"MaVolumeStrategy 选出 {len(selected)} 只股票")
        return selected
