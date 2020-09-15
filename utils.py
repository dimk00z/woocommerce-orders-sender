from pathlib import Path
import os
from dotenv import load_dotenv

import codecs
import smtplib
import yagmail
from yagmail.error import YagInvalidEmailAddress, YagConnectionClosed, YagAddressError

HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
    'accept-encoding': 'gzip, deflate, br',
    'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'cache-control': 'no-cache',
    'dnt': '1',
    'pragma': 'no-cache',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'none',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36'
}

TOUGH_EMAIL_SERVERS = [
    'gmail.com',
    'icloud.com',
    'hotmail.com'
]

with open(Path('.') / 'email_template.txt') as template_file:
    TEMPLATE_MESSAGE = template_file.read()


def load_params():
    env_path = Path('.') / '.env'
    load_dotenv(dotenv_path=env_path)
    params = {
        'telegram_bot_token': os.getenv("TELEGRAM_BOT_TOKEN"),
        'telegram_users': os.getenv("TELEGRAM_USERS_ID").split(','),
        'wc_user_key': os.getenv("WC_USER_KEY"),
        'wc_secret_key': os.getenv("WC_SECRET_KEY"),
        'wc_url': os.getenv("WC_URL"),
        'email_sender': os.getenv("EMAIL_SENDER"),
        'email_password': os.getenv("EMAIL_PASSWORD"),
        'email_display_name': os.getenv("EMAIL_DISPLAY_NAME"),
        'smtp_server': os.getenv("SMTP_SERVER"),
        'smtp_port': os.getenv("SMTP_PORT"),
    }
    return params


def send_email(params, to_email, subject, contents):
    try:
        yag = yagmail.SMTP(user={params['email_sender']: params["email_display_name"]},
                           password=params["email_password"],
                           smtp_ssl=True,
                           host=params['smtp_server'],
                           port=int(params['smtp_port']))
        yag.send(to=to_email, subject=subject, contents=contents)
        return True
    except (YagInvalidEmailAddress, YagConnectionClosed, smtplib.SMTPAuthenticationError,
            YagAddressError, smtplib.SMTPDataError, smtplib.SMTPServerDisconnected) as ex:
        print(ex)
        return False
