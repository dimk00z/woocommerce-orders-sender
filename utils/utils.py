from pathlib import Path
import smtplib
import yagmail
import logging.config
from yagmail.error import YagInvalidEmailAddress, YagConnectionClosed, YagAddressError


app_logger = logging.getLogger("app_logger")

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "dnt": "1",
    "pragma": "no-cache",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36",
}


with open(Path(".") / "email_template.txt") as template_file:
    TEMPLATE_MESSAGE = template_file.read()

with open(Path(".") / "telegram_manual.txt") as template_file:
    TELEGRAM_MANUAL = template_file.read()


def send_email(params, to_email, subject, contents, attachments):
    try:
        yag = yagmail.SMTP(
            user={params["email_sender"]: params["email_display_name"]},
            password=params["email_password"],
            smtp_ssl=True,
            host=params["smtp_server"],
            port=int(params["smtp_port"]),
        )
        yag.send(
            to=to_email, subject=subject, contents=contents, attachments=attachments
        )
        return True
    except (
        YagInvalidEmailAddress,
        YagConnectionClosed,
        smtplib.SMTPAuthenticationError,
        YagAddressError,
        smtplib.SMTPDataError,
        smtplib.SMTPServerDisconnected,
    ) as ex:
        app_logger.exception("Everything is bad:")
        return False
