import logging.config
import sys

import telebot

from utils.config import TelegramSettrings, get_settings


class TelegramHandler(logging.Handler):
    """Telegram logger

    Args:
        logging (_type_): _description_
    """

    def __init__(self, telegram_bot_token, telegram_users):
        logging.Handler.__init__(self)
        self.telegram_bot_token = telegram_bot_token
        self.telegram_users = telegram_users

    def emit(self, record):
        message = self.format(record)
        bot = telebot.TeleBot(self.telegram_bot_token)
        for user in self.telegram_users:
            if user:
                bot.send_message(user, message)


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
