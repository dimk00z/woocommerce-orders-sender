import logging.config
import telebot
from utils.env import load_params


class Telegram_Handler(logging.Handler):
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


format_string = '{asctime} - {levelname} - {name} - {module}:{funcName}:{lineno}- {message}'
telegram_params = load_params(['TELEGRAM_BOT_TOKEN',
                               'TELEGRAM_USERS_ID', ])
logger_config = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'std_formatter': {
            'format': format_string,
            'style': '{'
        }
    },
    'handlers': {
        'telegram_handler': {
            '()': Telegram_Handler,
            'formatter': 'std_formatter',
            'telegram_bot_token': telegram_params['telegram_bot_token'],
            'telegram_users': telegram_params['telegram_users_id']
        },
    },
    'loggers': {
        'app_logger': {
            'level': 'DEBUG',
            'handlers': ['telegram_handler'],
            'propagate': False
        }
    },
}
