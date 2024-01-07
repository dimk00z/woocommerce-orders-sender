import logging

import telebot

from utils.config import TelegramSettrings


class TelegramNoticifier:
    """Simple telegram noticifier"""

    def __init__(
        self, *, settings: TelegramSettrings, app_logger: logging.Logger
    ) -> None:
        self.settings: TelegramSettrings = settings
        self.app_logger: logging.Logger = app_logger
        self.bot = telebot.TeleBot(self.settings.bot_token)

    def send_result_to_telegram(self, *, message: str):
        """Send message for users

        Args:
            message (str): _description_
        """
        for user_id in self.settings.users_id:
            self.bot.send_message(chat_id=user_id, text=message)
