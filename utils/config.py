from functools import lru_cache
from typing import List

from pydantic import BaseSettings

from utils.email_config import EmailSettings


class TelegramSettrings(BaseSettings):
    bot_token: str
    users_id: List[str]
    proxy: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "TELEGRAM_"


class WoocommerceSettings(BaseSettings):
    user_key: str
    secret_key: str
    url: str
    debug_email: str = "dimk00z@gmail.com"
    redundant_phrase: str = " (материалы для преподавателей)"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "WC_"


class AppSettings(BaseSettings):
    debug: bool = False
    telegram_settings: TelegramSettrings = TelegramSettrings()
    woocommerce_settings: WoocommerceSettings = WoocommerceSettings()
    email_settings: EmailSettings = EmailSettings()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings():
    settings: AppSettings = AppSettings()
    settings.woocommerce_settings.url = (
        f"{settings.woocommerce_settings.url}/wp-json/wc/v3"
    )
    return settings
