from sequoia_x.strategy.base import BaseStrategy

class DummyStrategy(BaseStrategy):
    def run(self) -> list[str]:
        return []

def test_strategy_base():
    s = DummyStrategy(engine=None, settings=None)
    assert s.run() == []
