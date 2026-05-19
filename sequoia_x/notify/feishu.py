"""飞书通知模块：将选股结果通过 Webhook 推送至飞书群。"""

import json
from datetime import date

import requests

from sequoia_x.core.config import Settings
from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)


class FeishuNotifier:
    """飞书 Webhook 推送器。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _to_xueqiu_code(code: str) -> str:
        if code.startswith("6"):
            return f"SH{code}"
        elif code.startswith(("4", "8")):
            return f"BJ{code}"
        return f"SZ{code}"

    @staticmethod
    def _get_stock_names(symbols: list[str]) -> dict[str, str]:
        import baostock as bs
        bs.login()
        mapping = {}
        for code in symbols:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            rs = bs.query_stock_basic(code=f"{prefix}.{code}")
            while rs.next():
                row = rs.get_row_data()
                mapping[code] = row[1]
        bs.logout()
        return mapping

    def _build_card(self, symbols: list[str], strategy_name: str) -> dict:
        today = date.today().strftime("%Y-%m-%d")
        names = self._get_stock_names(symbols)
        links: list[str] = []
        for code in symbols:
            xq_code = self._to_xueqiu_code(code)
            name = names.get(code, xq_code)
            links.append(f"[{name}](https://xueqiu.com/S/{xq_code})")
        symbol_text = " ".join(links) if links else "（无选股结果）"
        return {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": f"📈 Sequoia-X 选股播报 | {strategy_name}"}, "template": "blue"},
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": f"**日期：** {today}\n**策略：** {strategy_name}\n**选股数量：** {len(symbols)}"}},
                    {"tag": "hr"},
                    {"tag": "div", "text": {"tag": "lark_md", "content": f"**选股列表：**\n{symbol_text}"}},
                ],
            },
        }

    def send(self, symbols: list[str], strategy_name: str, webhook_key: str = "default") -> None:
        url = self.settings.get_webhook_url(webhook_key)
        payload = self._build_card(symbols, strategy_name)
        try:
            resp = requests.post(url, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
            resp_json = resp.json()
            if resp.status_code != 200 or resp_json.get("code") != 0:
                logger.error(f"飞书推送失败 [{webhook_key}] HTTP状态={resp.status_code}")
            else:
                logger.info(f"飞书推送成功 [{webhook_key}]，共 {len(symbols)} 只股票")
        except requests.RequestException as exc:
            logger.error(f"飞书推送请求异常 [{webhook_key}]：{exc}")
