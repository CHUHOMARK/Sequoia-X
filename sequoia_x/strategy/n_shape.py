"""N字形态策略（买点版）：涨停/大阳线后洗盘，不破支撑，缩量末期/刚启动时买入。"""

import pandas as pd
from sequoia_x.core.logger import get_logger
from sequoia_x.strategy.base import BaseStrategy

logger = get_logger(__name__)


class NShapeStrategy(BaseStrategy):
    """N字形态策略（买点版）。"""
    webhook_key: str = "n_shape"
    _MIN_BARS: int = 20

    def run(self) -> list[str]:
        symbols = self.engine.get_local_symbols()
        candidates: list[str] = []
        for symbol in symbols:
            try:
                df = self.engine.get_ohlcv(symbol)
                if len(df) < self._MIN_BARS:
                    continue
                df_recent = df.tail(20).reset_index(drop=True)
                if len(df_recent) < 15:
                    continue
                df_recent['prev_close'] = df_recent['close'].shift(1)
                df_recent['change_pct'] = (df_recent['close'] - df_recent['prev_close']) / df_recent['prev_close'] * 100
                df_recent['vol_ma5'] = df_recent['volume'].rolling(5).mean()
                surge_idx = None
                surge_low = None
                surge_close = None
                for i in range(1, 8):
                    if i >= len(df_recent):
                        break
                    row = df_recent.iloc[-i]
                    if row['change_pct'] >= 7.0:
                        surge_idx = len(df_recent) - i
                        surge_low = row['low']
                        surge_close = row['close']
                        break
                if surge_idx is None or surge_idx < 5:
                    continue
                after_surge = df_recent.iloc[surge_idx + 1:]
                if len(after_surge) < 3:
                    continue
                min_low_after = after_surge['low'].min()
                if min_low_after < surge_low * 0.98:
                    continue
                wash_len = len(after_surge)
                if wash_len >= 4:
                    mid = wash_len // 2
                    vol_first_half = after_surge.iloc[:mid]['volume'].mean()
                    vol_second_half = after_surge.iloc[mid:]['volume'].mean()
                    if vol_first_half > 0 and vol_second_half > vol_first_half * 1.2:
                        continue
                current_close = df_recent.iloc[-1]['close']
                max_gain_from_support = (current_close - surge_low) / surge_low * 100
                if max_gain_from_support > 15.0:
                    continue
                last_3 = df_recent.tail(3)
                buy_signal = False
                signal_type = ""
                for idx in range(len(last_3)):
                    row = last_3.iloc[idx]
                    if (3.0 <= row['change_pct'] <= 7.0 and row['volume'] > row['vol_ma5'] * 1.5):
                        buy_signal = True
                        signal_type = "放量中阳"
                        break
                if not buy_signal and len(last_3) >= 2:
                    day1 = last_3.iloc[-2]
                    day2 = last_3.iloc[-1]
                    if (1.0 <= day1['change_pct'] <= 3.0 and 1.0 <= day2['change_pct'] <= 3.0 and day2['close'] > day1['close']):
                        buy_signal = True
                        signal_type = "连续小阳"
                if not buy_signal:
                    today = df_recent.iloc[-1]
                    body = abs(today['close'] - today['open'])
                    lower_shadow = min(today['open'], today['close']) - today['low']
                    total_range = today['high'] - today['low']
                    if total_range > 0:
                        if (lower_shadow / total_range > 0.5 and body / total_range < 0.3):
                            buy_signal = True
                            signal_type = "锤头线/十字星"
                if not buy_signal:
                    continue
                today_turnover = df_recent.iloc[-1]['turnover']
                if today_turnover < 50_000_000:
                    continue
                candidates.append(symbol)
            except Exception as exc:
                logger.warning(f"[{symbol}] NShapeStrategy 计算失败：{exc}")
                continue
        logger.info(f"NShapeStrategy 选出 {len(candidates)} 只股票")
        return candidates
