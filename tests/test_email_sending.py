import os
import tempfile
import unittest
from contextlib import ExitStack
from email import policy
from email.header import decode_header, make_header
from email.parser import Parser
from email.utils import parseaddr
from pathlib import Path
from smtplib import SMTPAuthenticationError
from types import SimpleNamespace
from unittest.mock import Mock, patch


# AppSettings constructs nested settings at import time.
with patch.dict(
    os.environ,
    {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TELEGRAM_USERS_ID": "[]",
        "WC_USER_KEY": "test-key",
        "WC_SECRET_KEY": "test-secret",
        "WC_URL": "https://example.com",
        "EMAIL_SENDER": "sender@example.com",
        "EMAIL_PASSWORD": "test-password",
        "EMAIL_DISPLAY_NAME": "Магазин",
    },
    clear=True,
):
    from services.orders_handler import OrdersHandler
    from utils.config import EmailSettings


class EmailSendingTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.ssl = stack.enter_context(patch("yagmail.sender.smtplib.SMTP_SSL"))
        self.plain = stack.enter_context(patch("yagmail.sender.smtplib.SMTP"))
        self.connection = self.ssl.return_value
        self.connection.sendmail.return_value = {}

    def settings(self, **kwargs):
        return EmailSettings(
            _env_file=None,
            sender="sender@example.com",
            password="test-password",
            display_name="Магазин",
            **kwargs,
        )

    def send(self, settings, attachments=None):
        handler = OrdersHandler(
            orders=[],
            settings=SimpleNamespace(
                email_settings=settings,
                woocommerce_settings=SimpleNamespace(
                    user_key="key", secret_key="secret"
                ),
            ),
            app_logger=Mock(),
        )
        return handler._send_email(
            to_email="buyer@example.com",
            subject="Ваш заказ",
            contents="<p>Спасибо за заказ</p>",
            attachments=attachments or [],
        )

    def test_missing_login_uses_sender(self):
        self.assertTrue(self.send(self.settings()))
        self.connection.login.assert_called_once_with(
            "sender@example.com", "test-password"
        )
        self.ssl.assert_called_once_with("smtp.yandex.ru", "465")

    def test_empty_login_uses_sender(self):
        os.environ["EMAIL_SMTP_LOGIN"] = ""
        self.assertTrue(self.send(self.settings()))
        self.connection.login.assert_called_once_with(
            "sender@example.com", "test-password"
        )

    def test_selectel_login_preserves_sender_html_and_attachment(self):
        os.environ["EMAIL_SMTP_LOGIN"] = "selectel-login"
        with tempfile.TemporaryDirectory() as directory:
            attachment = Path(directory) / "order.txt"
            attachment.write_text("Order contents", encoding="utf-8")
            self.assertTrue(
                self.send(
                    self.settings(smtp_server="smtp.mail.selcloud.ru", smtp_port=1127),
                    [str(attachment)],
                )
            )
        self.ssl.assert_called_once_with("smtp.mail.selcloud.ru", "1127")
        self.plain.assert_not_called()
        self.connection.starttls.assert_not_called()
        self.connection.login.assert_called_once_with("selectel-login", "test-password")
        sender, recipients, raw = self.connection.sendmail.call_args.args
        self.assertEqual(sender, "sender@example.com")
        self.assertEqual(recipients, ["buyer@example.com"])
        message = Parser(policy=policy.default).parsestr(raw)
        # yagmail 0.13 encodes the whole From header, including the address.
        raw_from = Parser().parsestr(raw)["From"]
        name, address = parseaddr(str(make_header(decode_header(raw_from))))
        self.assertEqual(address, "sender@example.com")
        self.assertEqual(name, "Магазин")
        self.assertEqual(str(message["Subject"]), "Ваш заказ")
        html = next(
            part for part in message.walk() if part.get_content_type() == "text/html"
        )
        self.assertIn("Спасибо за заказ", html.get_content())
        file_part = next(
            part for part in message.walk() if part.get_filename() == "order.txt"
        )
        self.assertEqual(file_part.get_payload(decode=True), b"Order contents")
        self.connection.quit.assert_called_once()

    def test_authentication_failure_does_not_send_and_closes_connection(self):
        self.connection.login.side_effect = SMTPAuthenticationError(
            535, b"Bad credentials"
        )
        self.assertFalse(self.send(self.settings()))
        self.connection.sendmail.assert_not_called()
        self.connection.quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
