import os
import logging
import tempfile
import unittest
from contextlib import ExitStack
from email import policy
from email.header import decode_header, make_header
from email.parser import Parser
from email.utils import parseaddr
from pathlib import Path
from smtplib import SMTPAuthenticationError
from smtplib import SMTPServerDisconnected
from types import SimpleNamespace
from unittest.mock import Mock, patch


# AppSettings constructs nested settings at import time.
with (
    patch.dict(
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
    ),
    patch("pydantic.env_settings.read_env_file", return_value={}),
):
    from models.order import Order
    from services.orders_handler import OrdersHandler
    from services.woocommerce_fetcher import WoocommerceFetcher
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

    def test_disconnected_server_returns_failure_after_retries(self):
        self.connection.sendmail.side_effect = SMTPServerDisconnected("Disconnected")
        with patch("yagmail.sender.time.sleep"):
            self.assertFalse(self.send(self.settings()))

    def test_refused_recipient_returns_failure(self):
        self.connection.sendmail.return_value = {"buyer@example.com": (550, b"Refused")}
        self.assertFalse(self.send(self.settings()))


class OrderPipelineTests(unittest.TestCase):
    def test_failed_send_does_not_update_woocommerce_and_report_says_so(self):
        order = self.order("104")
        handler = self.handler([order])
        with patch.object(handler, "_send_order_email", return_value=False), patch(
            "services.orders_handler.requests.Session"
        ) as session:
            with self.assertLogs("test_orders", level="INFO"):
                report = handler.handle(timeout=0)
        session.assert_not_called()
        self.assertFalse(order.status)
        self.assertIn("изменение статуса WooCommerce не запрашивалось", report)

    def test_successful_send_report_confirms_completed_only_after_update(self):
        order = self.order("105")
        handler = self.handler([order])
        handler.settings.woocommerce_settings.url = "https://example.com"
        with patch.object(handler, "_send_order_email", return_value=True), patch(
            "services.orders_handler.requests.Session"
        ) as session:
            session.return_value.put.return_value.status_code = 200
            with self.assertLogs("test_orders", level="INFO"):
                report = handler.handle(timeout=0)
        session.return_value.put.assert_called_once()
        self.assertTrue(order.status)
        self.assertIn("статус WooCommerce подтверждён: completed", report)

    def order(self, order_id):
        return Order(
            id=order_id,
            total=0,
            email="buyer@example.com",
            first_name="Test",
            last_name="Buyer",
        )

    def handler(self, orders):
        return OrdersHandler(
            orders=orders,
            settings=SimpleNamespace(
                woocommerce_settings=SimpleNamespace(
                    user_key="key", secret_key="secret"
                )
            ),
            app_logger=logging.getLogger("test_orders"),
        )

    def test_order_error_is_logged_and_next_order_is_processed(self):
        orders = [self.order("101"), self.order("102")]
        handler = self.handler(orders)
        with (
            patch.object(
                handler,
                "_send_order_email",
                side_effect=[FileNotFoundError("missing attachment"), True],
            ),
            patch.object(handler, "_close_order", return_value=True) as close,
        ):
            with self.assertLogs("test_orders", level="INFO") as logs:
                handler.handle(timeout=0)
        self.assertFalse(orders[0].status)
        self.assertTrue(orders[1].status)
        close.assert_called_once_with(order=orders[1])
        errors = [record for record in logs.records if record.levelno == logging.ERROR]
        self.assertTrue(
            any("101" in record.getMessage() and record.exc_info for record in errors)
        )
        self.assertIn("всего 2, успешно 1, с ошибками 1", logs.records[-1].getMessage())

    def test_sent_email_and_failed_status_are_reported_separately(self):
        order = self.order("103")
        handler = self.handler([order])
        handler.settings.woocommerce_settings.url = "https://example.com"
        with (
            patch.object(handler, "_send_order_email", return_value=True),
            patch("services.orders_handler.requests.Session") as session,
        ):
            session.return_value.put.return_value.status_code = 500
            with self.assertLogs("test_orders", level="INFO") as logs:
                handler.handle(timeout=0)
        self.assertFalse(order.status)
        self.assertTrue(
            any(
                "все письма отправлены" in record.getMessage()
                for record in logs.records
            )
        )
        self.assertTrue(
            any(
                record.levelno == logging.ERROR and "HTTP 500" in record.getMessage()
                for record in logs.records
            )
        )

    def test_fetch_error_is_not_reported_as_empty_queue(self):
        fetcher = WoocommerceFetcher(
            woocommerce_settings=SimpleNamespace(
                user_key="key",
                secret_key="secret",
                url="https://example.com",
                redundant_phrase="",
            ),
            app_logger=logging.getLogger("test_fetch"),
        )
        with patch.object(fetcher, "_fetch_wc_url", return_value=None):
            with self.assertLogs("test_fetch", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    fetcher.fetch_orders()


if __name__ == "__main__":
    unittest.main()
