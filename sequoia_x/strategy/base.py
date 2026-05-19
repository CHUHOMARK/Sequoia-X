"""策略基类模块：定义所有选股策略的抽象接口。"""

from abc import ABC, abstractmethod

from sequoia_x.core.config import Settings
from sequoia_x.data.engine import DataEngine


class BaseStrategy(ABC):
    """选股策略抽象基类。"""
    webhook_key: str = "default"

    def __init__(self, engine: DataEngine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings

    @abstractmethod
    def run(self) -> list[str]:
        """执行选股逻辑，返回选中的股票代码列表。"""
        ...
