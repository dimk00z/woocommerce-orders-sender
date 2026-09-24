import logging
from typing import List, Optional

import telebot
from telebot import apihelper

from services.proxy_loader import ProxyLoader
from utils.config import TelegramSettrings


class TelegramNoticifier:
    """Simple telegram noticifier"""

    MAX_PROXY_ATTEMPTS = 30

    def __init__(
        self, *, settings: TelegramSettrings, app_logger: logging.Logger
    ) -> None:
        self.settings: TelegramSettrings = settings
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

    def _proxy_candidates(self) -> List[str]:
        candidates: List[str] = []
        if self.settings.proxy:
            candidates.append(self.settings.proxy)

        # Loader returns https → socks5 → http
        for proxy in self.proxy_loader.act():
            if proxy.proxy and proxy.proxy not in candidates:
                candidates.append(proxy.proxy)
            if len(candidates) >= self.MAX_PROXY_ATTEMPTS:
                break

        if not candidates:
            candidates.append("")
        return candidates

    def _send_with_proxy(self, *, message: str, proxy_url: Optional[str]) -> bool:
        self._set_proxy(proxy_url or None)
        try:
            for user_id in self.settings.users_id:
                self.bot.send_message(chat_id=user_id, text=message)
            # console only — app_logger would recurse into TelegramHandler
            print(f"Telegram message sent via proxy={proxy_url or 'direct'}")
            return True
        except Exception as ex:
            print(f"Telegram send failed via proxy={proxy_url or 'direct'}: {ex}")
            return False

    def send_result_to_telegram(self, *, message: str):
        """Send message for users, trying proxies until one works."""
        for proxy_url in self._proxy_candidates():
            if self._send_with_proxy(message=message, proxy_url=proxy_url):
                return

        print("Failed to send telegram message via all proxies")
