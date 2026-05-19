"""定增公告监控策略：推送最近发布的定向增发公告。"""

from datetime import date, timedelta
import pandas as pd
from sequoia_x.core.logger import get_logger
from sequoia_x.strategy.base import BaseStrategy

logger = get_logger(__name__)


class PrivatePlacementStrategy(BaseStrategy):
    webhook_key: str = "private_placement"
    _LOOKBACK_DAYS: int = 7

    def run(self) -> list[str]:
        try:
            import akshare as ak
            df = ak.stock_qbzf_em()
        except Exception as exc:
            logger.error(f"PrivatePlacementStrategy 获取定增数据失败：{exc}")
            return []
        if df is None or df.empty:
            return []
        df = df[df["发行方式"] == "定向增发"]
        if df.empty:
            return []
        today = date.today()
        cutoff = today - timedelta(days=self._LOOKBACK_DAYS)
        df["发行日期"] = pd.to_datetime(df["发行日期"], errors="coerce")
        df = df.dropna(subset=["发行日期"])
        df = df[df["发行日期"].dt.date >= cutoff]
        if df.empty:
            return []
        df = df.sort_values("发行日期", ascending=False)
        symbols = df["股票代码"].astype(str).str.extract(r"(\d{6})")[0].dropna().tolist()
        seen = set()
        unique_symbols = []
        for s in symbols:
            if s not in seen:
                seen.add(s)
                unique_symbols.append(s)
        logger.info(f"PrivatePlacementStrategy 选出 {len(unique_symbols)} 只股票")
        return unique_symbols
