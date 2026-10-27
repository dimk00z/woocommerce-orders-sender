"""Send a test message using the application's SMTP configuration."""

import argparse
import logging

from pydantic import Field, ValidationError

from services.email_sender import EmailSMTP
from utils.email_config import EmailSettings
from utils.log_context import RunContextFilter, SafeFormatter, start_run

logger = logging.getLogger("send_test_email")


class TestEmailSettings(EmailSettings):
    test_email: str = Field("", env="TEST_EMAIL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Отправить тестовое письмо с текущими SMTP-настройками из .env."
    )
    parser.add_argument(
        "recipient", nargs="?", help="Адрес получателя (по умолчанию TEST_EMAIL)."
    )
    args = parser.parse_args(argv)
    start_run()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(RunContextFilter())
        handler.setFormatter(
            SafeFormatter(
                "%(asctime)s - %(levelname)s - запуск %(run_id)s, PID %(process)d - %(message)s"
            )
        )

    try:
        settings = TestEmailSettings()
    except ValidationError as error:
        logger.error("Ошибка почтовых настроек: %s", error)
        return 1

    recipient = (
        args.recipient if args.recipient is not None else settings.test_email
    ).strip()
    if not recipient:
        logger.error(
            "Укажите TEST_EMAIL в .env или адрес получателя аргументом командной строки"
        )
        return 1

    logger.info(
        "Отправка тестового письма: от %s для %s, SMTP %s:%s (SSL)",
        settings.sender,
        recipient,
        settings.smtp_server,
        settings.smtp_port,
    )
    try:
        with EmailSMTP(
            user={settings.sender: settings.display_name},
            smtp_login=settings.smtp_login,
            password=settings.password,
            host=settings.smtp_server,
            port=settings.smtp_port,
            smtp_ssl=True,
            timeout=30,
            diagnostic_logger=logger,
            context=f"Тестовое письмо для {recipient}",
        ) as smtp:
            result = smtp.send(
                to=recipient,
                subject="Тест SMTP — WooCommerce orders sender",
                contents="Тестовое письмо для проверки SMTP-настроек отправки почты.",
            )
        if result is False or result:
            logger.error(
                "Тестовое письмо не отправлено: SMTP вернул неуспешный результат"
            )
            return 1
    except Exception:
        logger.exception("Ошибка отправки тестового письма для %s", recipient)
        return 1

    logger.info(
        "Тестовое письмо для %s принято SMTP-сервером; проверьте входящие и спам",
        recipient,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
