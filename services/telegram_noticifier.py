import logging
import re
from typing import Optional

import telebot
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import SSLError, Timeout
from telebot import apihelper
from urllib3.exceptions import MaxRetryError

from services.proxy_loader import ProxyLoader
from utils.config import TelegramSettrings
from utils.log_context import redact, register_log_secret
from utils.telegram_text import split_telegram_html


def format_telegram_send_error(ex: BaseException) -> str:
    """Short safe error text (no bot token / full request URL)."""
    if isinstance(ex, MaxRetryError) or (
        isinstance(ex, RequestsConnectionError) and "Max retries exceeded" in str(ex)
    ):
        cause = ex.args[0] if ex.args else None
        reason = getattr(cause, "reason", None) or cause or ex
        reason_text = re.sub(r"/bot[^/\s?]+", "/bot***", str(reason))
        if "timed out" in reason_text.lower() or "ConnectTimeout" in reason_text:
            return "Max retries exceeded (connect timeout)"
        if "SSL" in reason_text or "Certificate" in reason_text:
            return "Max retries exceeded (ssl error)"
        if "unreachable" in reason_text.lower():
            return "Max retries exceeded (network unreachable)"
        return f"Max retries exceeded ({reason_text[:120]})"

    if isinstance(ex, (SSLError, Timeout, RequestsConnectionError)):
        return re.sub(r"/bot[^/\s?]+", "/bot***", str(ex))[:160]

    return re.sub(r"/bot[^/\s?]+", "/bot***", str(ex))[:160]


class TelegramNoticifier:
    """Simple telegram noticifier"""

    MAX_PROXY_ATTEMPTS = 30

    def __init__(
        self, *, settings: TelegramSettrings, app_logger: logging.Logger
    ) -> None:
        self.settings: TelegramSettrings = settings
        register_log_secret(settings.bot_token)
        self.app_logger: logging.Logger = app_logger
        apihelper.CONNECT_TIMEOUT = 10
        apihelper.READ_TIMEOUT = 15
        self.bot = telebot.TeleBot(self.settings.bot_token)
        self.proxy_loader = ProxyLoader()

    def _set_proxy(self, proxy_url: Optional[str]) -> None:
        if proxy_url:
            apihelper.proxy = {
                "http": proxy_url,
                "https": proxy_url,
            }
        else:
            apihelper.proxy = None

    def _send_with_proxy(
        self, *, message: str, proxy_url: Optional[str], delivered=None
    ) -> bool:
        if delivered is None:
            delivered = set()
        self._set_proxy(proxy_url or None)
        try:
            for user_id in self.settings.users_id:
                if not user_id:
                    continue
                for index, part in enumerate(split_telegram_html(redact(message))):
                    if (user_id, index) not in delivered:
                        self.bot.send_message(
                            chat_id=user_id, text=part, parse_mode="HTML"
                        )
                        delivered.add((user_id, index))
            self.app_logger.info(
                "Отчёт Telegram отправлен, подключение: %s",
                "прокси" if proxy_url else "напрямую",
                extra={"console_only": True},
            )
            if proxy_url:
                self.proxy_loader.save_last_success(proxy_url)
            return True
        except (RequestsConnectionError, MaxRetryError, SSLError, Timeout) as ex:
            self.app_logger.warning(
                "Не удалось отправить отчёт Telegram (%s): %s",
                "прокси" if proxy_url else "напрямую",
                format_telegram_send_error(ex),
                extra={"console_only": True},
            )
            return False
        except Exception as ex:
            self.app_logger.warning(
                "Не удалось отправить отчёт Telegram (%s): %s",
                "прокси" if proxy_url else "напрямую",
                format_telegram_send_error(ex),
                extra={"console_only": True},
            )
            return False

    def send_result_to_telegram(self, *, message: str):
        """Send message for users, trying proxies until one works."""
        self.app_logger.info(
            "Отправка итогового отчёта в Telegram", extra={"console_only": True}
        )
        delivered = set()
        for proxy_url in self.proxy_loader.candidates(
            configured=self.settings.proxy,
            limit=self.MAX_PROXY_ATTEMPTS,
        ):
            if self._send_with_proxy(
                message=message, proxy_url=proxy_url, delivered=delivered
            ):
                return

        # The Telegram logging handler would repeat the same failed network calls.
        self.app_logger.warning(
            "Отчёт Telegram не отправлен: все варианты подключения исчерпаны",
            extra={"console_only": True},
        )
