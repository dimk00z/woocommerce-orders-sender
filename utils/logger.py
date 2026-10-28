import logging.config
import sys
from typing import List, Optional

import telebot
from telebot import apihelper

from services.proxy_loader import ProxyLoader
from utils.config import TelegramSettrings, get_settings
from utils.log_context import (
    RunContextFilter,
    SafeFormatter,
    TelegramLogFilter,
    register_log_secret,
)
from utils.telegram_text import split_telegram_text


class TelegramHandler(logging.Handler):
    """Telegram logger that tries proxies when Telegram is unreachable."""

    MAX_PROXY_ATTEMPTS = 30

    def __init__(self, telegram_bot_token, telegram_users, telegram_proxy: str = ""):
        logging.Handler.__init__(self)
        self.telegram_bot_token = telegram_bot_token
        register_log_secret(telegram_bot_token)
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
        self._candidates = self._proxy_loader.candidates(
            configured=self.telegram_proxy,
            limit=self.MAX_PROXY_ATTEMPTS,
        )
        return self._candidates

    def _send_with_proxy(
        self, *, message: str, proxy_url: Optional[str], delivered=None
    ) -> bool:
        if delivered is None:
            delivered = set()
        self._set_proxy(proxy_url or None)
        try:
            for user in self.telegram_users:
                if user:
                    for index, part in enumerate(split_telegram_text(message)):
                        if (user, index) not in delivered:
                            self.bot.send_message(user, part)
                            delivered.add((user, index))
            if proxy_url:
                self._proxy_loader.save_last_success(proxy_url)
            return True
        except Exception as error:
            from services.telegram_noticifier import format_telegram_send_error

            logging.getLogger("app_logger").warning(
                "Не удалось передать лог в Telegram: %s",
                format_telegram_send_error(error),
                extra={"console_only": True},
            )
            return False

    def emit(self, record):
        try:
            message = self.format(record)
            delivered = set()
            for proxy_url in self._proxy_candidates():
                if self._send_with_proxy(
                    message=message, proxy_url=proxy_url, delivered=delivered
                ):
                    return
            logging.getLogger("app_logger").warning(
                "Лог Telegram не доставлен: все варианты подключения исчерпаны",
                extra={"console_only": True},
            )
        except Exception:
            self.handleError(record)


format_string = "{asctime} - {levelname} - запуск {run_id}, PID {process} - {module}:{funcName}:{lineno} - {message}"

telegram_params: TelegramSettrings = get_settings().telegram_settings
logger_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "std_formatter": {"()": SafeFormatter, "format": format_string, "style": "{"}
    },
    "filters": {
        "run_context": {"()": RunContextFilter},
        "telegram_context": {"()": TelegramLogFilter},
    },
    "handlers": {
        "telegram_handler": {
            "()": TelegramHandler,
            "level": "ERROR",
            "filters": ["telegram_context"],
            "formatter": "std_formatter",
            "telegram_bot_token": telegram_params.bot_token,
            "telegram_users": telegram_params.users_id,
            "telegram_proxy": telegram_params.proxy,
        },
        "console_stdout": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "filters": ["run_context"],
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
