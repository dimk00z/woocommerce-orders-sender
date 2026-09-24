import logging.config
import sys
from typing import List, Optional

import telebot
from telebot import apihelper

from services.proxy_loader import ProxyLoader
from utils.config import TelegramSettrings, get_settings


class TelegramHandler(logging.Handler):
    """Telegram logger that tries proxies when Telegram is unreachable."""

    MAX_PROXY_ATTEMPTS = 30

    def __init__(self, telegram_bot_token, telegram_users, telegram_proxy: str = ""):
        logging.Handler.__init__(self)
        self.telegram_bot_token = telegram_bot_token
        self.telegram_users = telegram_users
        self.telegram_proxy = telegram_proxy
        self.bot = telebot.TeleBot(telegram_bot_token)
        self._proxy_loader = ProxyLoader()
        self._candidates: Optional[List[str]] = None
        apihelper.CONNECT_TIMEOUT = 10
        apihelper.READ_TIMEOUT = 15

    def _set_proxy(self, proxy_url: Optional[str]) -> None:
        if proxy_url:
            apihelper.proxy = {"http": proxy_url, "https": proxy_url}
        else:
            apihelper.proxy = None

    def _proxy_candidates(self) -> List[str]:
        if self._candidates is not None:
            return self._candidates

        candidates: List[str] = []
        if self.telegram_proxy:
            candidates.append(self.telegram_proxy)

        for proxy in self._proxy_loader.act():
            if proxy.proxy and proxy.proxy not in candidates:
                candidates.append(proxy.proxy)
            if len(candidates) >= self.MAX_PROXY_ATTEMPTS:
                break

        if not candidates:
            candidates.append("")
        self._candidates = candidates
        return candidates

    def _send_with_proxy(self, *, message: str, proxy_url: Optional[str]) -> bool:
        self._set_proxy(proxy_url or None)
        try:
            for user in self.telegram_users:
                if user:
                    self.bot.send_message(user, message)
            return True
        except Exception:
            return False

    def emit(self, record):
        try:
            message = self.format(record)
            for proxy_url in self._proxy_candidates():
                if self._send_with_proxy(message=message, proxy_url=proxy_url):
                    return
        except Exception:
            self.handleError(record)


format_string = (
    "{asctime} - {levelname} - {name} - {module}:{funcName}:{lineno}- {message}"
)

telegram_params: TelegramSettrings = get_settings().telegram_settings
logger_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"std_formatter": {"format": format_string, "style": "{"}},
    "handlers": {
        "telegram_handler": {
            "()": TelegramHandler,
            "formatter": "std_formatter",
            "telegram_bot_token": telegram_params.bot_token,
            "telegram_users": telegram_params.users_id,
            "telegram_proxy": telegram_params.proxy,
        },
        "console_stdout": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "std_formatter",
            "stream": sys.stdout,
        },
    },
    "loggers": {
        "app_logger": {
            "level": "DEBUG",
            "handlers": [
                "telegram_handler",
                "console_stdout",
            ],
            "propagate": False,
        }
    },
}
