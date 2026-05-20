"""Sequoia-X V2 主程序入口。"""

import argparse
import sys
from dotenv import load_dotenv
load_dotenv()

from datetime import date
import socket
socket.setdefaulttimeout(10.0)

from sequoia_x.core.config import get_settings
from sequoia_x.core.logger import get_logger
from sequoia_x.data.engine import DataEngine
from sequoia_x.notify.feishu import FeishuNotifier
from sequoia_x.strategy.base import BaseStrategy
from sequoia_x.strategy.high_tight_flag import HighTightFlagStrategy
from sequoia_x.strategy.limit_up_shakeout import LimitUpShakeoutStrategy
from sequoia_x.strategy.ma_volume import MaVolumeStrategy
from sequoia_x.strategy.n_shape import NShapeStrategy
from sequoia_x.strategy.turtle_trade import TurtleTradeStrategy
from sequoia_x.strategy.uptrend_limit_down import UptrendLimitDownStrategy
from sequoia_x.strategy.rps_breakout import RpsBreakoutStrategy
from sequoia_x.strategy.private_placement import PrivatePlacementStrategy


def _run_daily(settings, logger) -> None:
    engine = DataEngine(settings)
    logger.info("开始拉取最新快照...")
    count = engine.sync_today_bulk()
    logger.info(f"快照同步完成，写入 {count} 只股票")
    strategies: list[BaseStrategy] = [
        MaVolumeStrategy(engine=engine, settings=settings),
        TurtleTradeStrategy(engine=engine, settings=settings),
        HighTightFlagStrategy(engine=engine, settings=settings),
        LimitUpShakeoutStrategy(engine=engine, settings=settings),
        UptrendLimitDownStrategy(engine=engine, settings=settings),
        RpsBreakoutStrategy(engine=engine, settings=settings),
        PrivatePlacementStrategy(engine=engine, settings=settings),
        NShapeStrategy(engine=engine, settings=settings),
    ]
    notifier = FeishuNotifier(settings)
    for strategy in strategies:
        strategy_name = type(strategy).__name__
        logger.info(f"执行策略：{strategy_name}")
        selected: list[str] = strategy.run()
        logger.info(f"{strategy_name} 选出 {len(selected)} 只股票")
        if selected:
            notifier.send(symbols=selected, strategy_name=strategy_name, webhook_key=strategy.webhook_key)
        else:
            logger.info(f"{strategy_name} 无选股结果，跳过推送")


def _run_backfill(settings, logger) -> None:
    logger.info("进入回填模式...")
    engine = DataEngine(settings)
    all_symbols = engine.get_all_symbols()
    engine.backfill(all_symbols)
    logger.info("Sequoia-X V2 回填模式运行完成")


def _run_snapshot(args) -> None:
    from sequoia_x.modules.snapshot import run as snapshot_run
    section = args.snapshot if args.snapshot else "all"
    snapshot_run(section=section, use_json=args.json)


def _run_calendar(args) -> None:
    from sequoia_x.modules.calendar import run as calendar_run
    section = args.calendar if args.calendar else "week"
    calendar_run(section=section, args=args.calendar_args or [], use_json=args.json)


def _run_margin(args) -> None:
    from sequoia_x.modules.margin import run as margin_run
    section = args.margin if args.margin else "all"
    margin_run(section=section, use_json=args.json)


def _run_news(args) -> None:
    from sequoia_x.modules.news import run as news_run
    news_run(limit=args.news or 20, use_json=args.json)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sequoia-X V2 — A股量化选股系统 + 市场数据助手")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--json", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--snapshot", nargs="?", const="all")
    group.add_argument("--calendar", nargs="?", const="week")
    group.add_argument("--calendar-args", nargs="*")
    group.add_argument("--margin", nargs="?", const="all")
    group.add_argument("--news", nargs="?", const="20", type=int)
    args = parser.parse_args()
    try:
        settings = get_settings()
        logger = get_logger(__name__)
        logger.info("Sequoia-X V2 启动")
        has_module_cmd = any([args.snapshot is not None, args.calendar is not None, args.margin is not None, args.news is not None])
        if args.backfill:
            _run_backfill(settings, logger)
        elif has_module_cmd:
            if args.snapshot is not None: _run_snapshot(args)
            elif args.calendar is not None: _run_calendar(args)
            elif args.margin is not None: _run_margin(args)
            elif args.news is not None: _run_news(args)
        else:
            _run_daily(settings, logger)
    except Exception:
        try:
            _logger = get_logger(__name__)
            _logger.exception("主流程发生未捕获异常")
        except Exception:
            import traceback; traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
