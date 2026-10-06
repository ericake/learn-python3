"""运行配置：全部从环境变量或 .env 读取，密钥不写进代码。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # 基础
    app_env: str = "dev"  # dev 时登录接口会直接返回验证码，方便本地调试
    app_secret_key: str = "change-me-in-production"
    timezone: str = "Asia/Shanghai"
    database_url: str = f"sqlite:///{BASE_DIR / 'shengyan.db'}"
    admin_phone: str = "13800000000"
    admin_name: str = "管理员"
    public_base_url: str = "http://localhost:8000"  # 预警消息里“在系统中处理”的链接前缀
    enable_scheduler: bool = True

    # TikHub（小红书数据源）
    tikhub_api_key: str = ""
    tikhub_base_url: str = "https://api.tikhub.io"
    tikhub_search_path: str = "/api/v1/xiaohongshu/app_v2/search_notes"
    tikhub_concurrency: int = 2
    tikhub_min_interval_ms: int = 1000
    tikhub_timeout_s: float = 15.0
    crawler_mode: str = "auto"  # auto：有 Token 用 tikhub，否则 mock

    # 采集调度
    crawl_interval_min: int = 10
    crawl_max_pages: int = 3
    backfill_days: int = 3
    backfill_max_pages: int = 10
    retention_days: int = 90

    # 情感判断（DeepSeek，OpenAI 兼容接口）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_timeout_s: float = 30.0
    sentiment_mode: str = "auto"  # auto：有 Key 用 llm，否则 rule

    # 邮件
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # 套餐限制（PRD）
    max_groups: int = 3
    max_words_per_group: int = 20

    @property
    def effective_crawler_mode(self) -> str:
        if self.crawler_mode != "auto":
            return self.crawler_mode
        return "tikhub" if self.tikhub_api_key else "mock"

    @property
    def effective_sentiment_mode(self) -> str:
        if self.sentiment_mode != "auto":
            return self.sentiment_mode
        return "llm" if self.llm_api_key else "rule"


@lru_cache
def get_settings() -> Settings:
    return Settings()
