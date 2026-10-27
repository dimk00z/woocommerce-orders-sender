import logging
import logging.config
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from smtplib import SMTPServerDisconnected
from types import SimpleNamespace
from unittest.mock import Mock, call, mock_open, patch

with (
    patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "123:test",
            "TELEGRAM_USERS_ID": "[]",
            "WC_USER_KEY": "key",
            "WC_SECRET_KEY": "secret",
            "WC_URL": "https://example.com",
            "EMAIL_SENDER": "sender@example.com",
            "EMAIL_PASSWORD": "password",
            "EMAIL_DISPLAY_NAME": "Shop",
        },
        clear=True,
    ),
    patch("pydantic.env_settings.read_env_file", return_value={}),
):
    from models.order import Order, ProductFile
    from services.email_sender import EmailSMTP
    from services.orders_handler import OrdersHandler
    from services.telegram_noticifier import TelegramNoticifier
    from utils.config import EmailSettings
    from utils.logger import TelegramHandler, logger_config


class SMTPDiagnosticsTests(unittest.TestCase):
    def test_disconnect_during_authentication_has_stage_and_order(self):
        with patch("yagmail.sender.smtplib.SMTP_SSL") as connection:
            connection.return_value.login.side_effect = SMTPServerDisconnected(
                "Connection unexpectedly closed"
            )
            with self.assertLogs("smtp_diagnostics", level="INFO") as logs:
                with EmailSMTP(
                    user="sender@example.com",
                    password="secret-password",
                    diagnostic_logger=logging.getLogger("smtp_diagnostics"),
                    context="Заказ №47065, часть 1/2",
                ) as smtp:
                    with self.assertRaises(SMTPServerDisconnected):
                        smtp.send(to="buyer@example.com", contents="private body")
        text = "\n".join(logs.output)
        self.assertIn("авторизация", text)
        self.assertIn("47065", text)
        self.assertIn("SMTPServerDisconnected", smtp.last_error)
        self.assertNotIn("secret-password", text)
        self.assertNotIn("private body", text)
        connection.return_value.sendmail.assert_not_called()

    def test_all_transfer_attempts_are_visible_without_changing_retries(self):
        with (
            patch("yagmail.sender.smtplib.SMTP_SSL") as connection,
            patch("yagmail.sender.time.sleep") as sleep,
        ):
            connection.return_value.sendmail.side_effect = SMTPServerDisconnected(
                "Disconnected"
            )
            with self.assertLogs("smtp_diagnostics", level="INFO") as logs:
                with EmailSMTP(
                    user="sender@example.com",
                    password="password",
                    diagnostic_logger=logging.getLogger("smtp_diagnostics"),
                    context="Заказ №47065, часть 2/2",
                ) as smtp:
                    self.assertIs(
                        smtp.send(to="buyer@example.com", contents="test"), False
                    )
        text = "\n".join(logs.output)
        for attempt in ("1/3", "2/3", "3/3"):
            self.assertIn(attempt, text)
        self.assertIn("приём письма не подтверждён", smtp.last_error)
        self.assertEqual(connection.return_value.sendmail.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(3), call(6), call(9)])


class OrderDiagnosticsTests(unittest.TestCase):
    def test_partial_send_keeps_results_and_smtp_reason_in_report(self):
        order = Order(
            id="47065",
            total=0,
            email="buyer@example.com",
            first_name="Test",
            last_name="Buyer",
        )
        settings = SimpleNamespace(
            email_settings=EmailSettings(
                _env_file=None,
                sender="sender@example.com",
                password="password",
                display_name="Shop",
                max_attachment_size=1,
            ),
            woocommerce_settings=SimpleNamespace(user_key="key", secret_key="secret"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for name in ("one.txt", "two.txt"):
                path = Path(directory) / name
                path.write_text("test")
                order.total_files.append(ProductFile(file_name=str(path), file_size=4))
            handler = OrdersHandler(
                orders=[order],
                settings=settings,
                app_logger=logging.getLogger("order_diagnostics"),
            )
            with (
                patch.object(
                    OrdersHandler,
                    "_split_files",
                    return_value=[
                        [order.total_files[0].file_name],
                        [order.total_files[1].file_name],
                    ],
                ),
                patch("yagmail.sender.smtplib.SMTP_SSL") as connection,
                patch.object(handler, "_close_order") as close,
                patch(
                    "services.orders_handler.open",
                    mock_open(read_data=b"<p>Test</p>"),
                    create=True,
                ),
            ):
                connection.return_value.sendmail.side_effect = [
                    {},
                    {"buyer@example.com": (550, b"Mailbox unavailable")},
                ]
                with self.assertLogs("order_diagnostics", level="INFO"):
                    report = handler.handle(timeout=0)
        self.assertIn("часть 1/2", report)
        self.assertIn("часть 2/2", report)
        self.assertIn("550", report)
        self.assertIn("Mailbox unavailable", report)
        self.assertIn("успешно 0", report)
        self.assertIn("с ошибками 1", report)
        close.assert_not_called()


class TelegramTransportTests(unittest.TestCase):
    def test_configured_formatter_includes_run_id_pid_and_traceback(self):
        from utils.log_context import RunContextFilter, start_run

        run_id = start_run()
        formatter = logging.config.DictConfigurator(logger_config).configure_formatter(
            deepcopy(logger_config["formatters"]["std_formatter"])
        )
        try:
            raise RuntimeError("SMTP disconnected")
        except RuntimeError:
            import sys

            record = logging.LogRecord(
                "test", logging.ERROR, __file__, 1, "Заказ №123", (), sys.exc_info()
            )
        RunContextFilter().filter(record)
        text = formatter.format(record)
        self.assertIn(run_id, text)
        self.assertIn(f"PID {os.getpid()}", text)
        self.assertIn("Traceback", text)

    def test_failed_telegram_transport_does_not_log_back_to_telegram(self):
        handler = TelegramHandler("123:test", ["user"])
        for spec in logger_config["handlers"]["telegram_handler"]["filters"]:
            handler.addFilter(logger_config["filters"][spec]["()"]())
        logger = logging.getLogger("app_logger")
        with (
            patch.object(logger, "handlers", [handler]),
            patch.object(logger, "level", logging.INFO),
            patch.object(logger, "propagate", False),
            patch.object(
                handler, "_proxy_candidates", return_value=["", "http://proxy"]
            ),
            patch.object(
                handler.bot, "send_message", side_effect=RuntimeError("Telegram down")
            ) as send,
        ):
            logger.info("Проверка уведомления")
        self.assertEqual(send.call_count, 2)

    def test_proxy_fallback_does_not_repeat_delivered_chunks(self):
        handler = TelegramHandler("123:test", ["user"])
        record = logging.makeLogRecord({"msg": "x" * 7001})
        with (
            patch.object(
                handler, "_proxy_candidates", return_value=["", "http://proxy"]
            ),
            patch.object(handler._proxy_loader, "save_last_success"),
            patch.object(
                handler.bot,
                "send_message",
                side_effect=[None, RuntimeError("Disconnected"), None, None],
            ) as send,
        ):
            with self.assertLogs("app_logger", level="WARNING"):
                handler.emit(record)
        self.assertEqual(
            [len(item.args[1]) for item in send.call_args_list], [3500, 3500, 3500, 1]
        )

    def test_formatter_redacts_secrets_from_traceback(self):
        from utils.log_context import SafeFormatter, register_log_secret

        register_log_secret("private-smtp-password")
        try:
            raise RuntimeError("private-smtp-password /bot123:secret/sendMessage")
        except RuntimeError:
            import sys

            record = logging.LogRecord(
                "test", logging.ERROR, __file__, 1, "SMTP failed", (), sys.exc_info()
            )
        text = SafeFormatter().format(record)
        self.assertIn("Traceback", text)
        self.assertNotIn("private-smtp-password", text)
        self.assertNotIn("123:secret", text)

    def test_info_is_sent_debug_is_not_and_transport_messages_are_filtered(self):
        handler = TelegramHandler("123:test", ["user"])
        handler.setLevel(logger_config["handlers"]["telegram_handler"]["level"])
        for spec in logger_config["handlers"]["telegram_handler"].get("filters", []):
            handler.addFilter(logger_config["filters"][spec]["()"]())
        logger = logging.Logger("diagnostics", logging.DEBUG)
        logger.addHandler(handler)
        with (
            patch.object(handler, "_proxy_candidates", return_value=[""]),
            patch.object(handler.bot, "send_message") as send,
        ):
            logger.info("Заказ загружен")
            logger.debug("Технический запрос")
            logger.warning("Telegram unavailable", extra={"console_only": True})
        self.assertEqual(send.call_count, 1)
        self.assertIn("Заказ загружен", send.call_args.args[1])

    def test_handler_splits_long_traceback_without_losing_text(self):
        handler = TelegramHandler("123:test", ["user"])
        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1, "Ошибка " + "я😀" * 5000, (), None
        )
        expected = handler.format(record)
        with (
            patch.object(handler, "_proxy_candidates", return_value=[""]),
            patch.object(handler.bot, "send_message") as send,
        ):
            handler.emit(record)
        parts = [item.args[1] for item in send.call_args_list]
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(parts), expected)
        self.assertTrue(
            all(len(part.encode("utf-16-le")) // 2 <= 3500 for part in parts)
        )

    def test_report_is_split_and_transport_logs_are_console_only(self):
        notifier = TelegramNoticifier(
            settings=SimpleNamespace(bot_token="123:test", users_id=["user"], proxy=""),
            app_logger=Mock(),
        )
        with patch.object(notifier.bot, "send_message") as send:
            self.assertTrue(
                notifier._send_with_proxy(message="x" * 8000, proxy_url=None)
            )
        self.assertEqual(
            "".join(item.kwargs["text"] for item in send.call_args_list), "x" * 8000
        )
        self.assertGreater(send.call_count, 1)
        self.assertTrue(
            notifier.app_logger.info.call_args.kwargs["extra"]["console_only"]
        )

    def test_run_ids_are_distinct_and_added_to_records(self):
        from utils.log_context import RunContextFilter, start_run

        first = start_run()
        record = logging.makeLogRecord({"msg": "test"})
        RunContextFilter().filter(record)
        second = start_run()
        self.assertNotEqual(first, second)
        self.assertEqual(record.run_id, first)


if __name__ == "__main__":
    unittest.main()
