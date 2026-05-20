"""配置管理模块：通过 pydantic-settings 从环境变量或 .env 文件加载系统配置。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_path: str = "data/sequoia_v2.db"
    start_date: str = "2024-01-01"
    tickflow_api_key: str
    feishu_webhook_url: str = ""
    strategy_webhooks: dict[str, str] = {}

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore",
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, **kwargs):
        from pydantic_settings import EnvSettingsSource
        import os
        sources = super().settings_customise_sources(settings_cls, **kwargs)
        prefix = "STRATEGY_WEBHOOK_"
        webhooks: dict[str, str] = {}
        for key, value in os.environ.items():
            if key.upper().startswith(prefix):
                strategy_key = key[len(prefix):].lower()
                webhooks[strategy_key] = value
        if webhooks:
            os.environ.setdefault("_STRATEGY_WEBHOOKS_PARSED", "1")
            cls._parsed_strategy_webhooks = webhooks
        return sources

    def model_post_init(self, __context: object) -> None:
        import os
        prefix = "STRATEGY_WEBHOOK_"
        webhooks: dict[str, str] = dict(self.strategy_webhooks)
        for key, value in os.environ.items():
            if key.upper().startswith(prefix):
                strategy_key = key[len(prefix):].lower()
                webhooks[strategy_key] = value
        object.__setattr__(self, "strategy_webhooks", webhooks)

    def get_webhook_url(self, webhook_key: str) -> str:
        return self.strategy_webhooks.get(webhook_key.lower(), self.feishu_webhook_url)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
