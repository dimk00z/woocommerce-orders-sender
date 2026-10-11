import importlib
import os
import tempfile
import unittest
from contextlib import ExitStack
from email import policy
from email.parser import Parser
from pathlib import Path
from smtplib import SMTPAuthenticationError
from unittest.mock import patch


class TestEmailScriptTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        directory = stack.enter_context(tempfile.TemporaryDirectory())
        previous = os.getcwd()
        os.chdir(directory)
        stack.callback(os.chdir, previous)
        stack.enter_context(patch.dict(os.environ, {}, clear=True))
        Path(".env").write_text(
            "EMAIL_SENDER=sender@example.com\n"
            "EMAIL_PASSWORD=test-password\n"
            "EMAIL_DISPLAY_NAME=Shop\n"
            "EMAIL_SMTP_LOGIN=selectel-login\n"
            "EMAIL_SMTP_SERVER=smtp.mail.selcloud.ru\n"
            "EMAIL_SMTP_PORT=1127\n"
            "TEST_EMAIL=buyer@example.com\n",
            encoding="utf-8",
        )
        self.script = importlib.import_module("send_test_email")
        self.ssl = stack.enter_context(patch("yagmail.sender.smtplib.SMTP_SSL"))
        self.connection = self.ssl.return_value
        self.connection.sendmail.return_value = {}

    def test_reads_dotenv_and_sends_without_woocommerce_or_telegram_settings(self):
        with self.assertLogs("send_test_email", level="INFO"):
            self.assertEqual(self.script.main([]), 0)
        self.connection.login.assert_called_once_with("selectel-login", "test-password")
        sender, recipients, raw = self.connection.sendmail.call_args.args
        self.assertEqual(sender, "sender@example.com")
        self.assertEqual(recipients, ["buyer@example.com"])
        message = Parser(policy=policy.default).parsestr(raw)
        self.assertIn("SMTP", str(message["Subject"]))
        body = next(
            part for part in message.walk() if part.get_content_type() == "text/plain"
        )
        self.assertIn("SMTP", body.get_content())
        self.connection.quit.assert_called_once()

    def test_argument_overrides_default_recipient(self):
        with self.assertLogs("send_test_email", level="INFO"):
            self.assertEqual(self.script.main(["other@example.com"]), 0)
        self.assertEqual(
            self.connection.sendmail.call_args.args[1], ["other@example.com"]
        )

    def test_environment_overrides_dotenv_recipient(self):
        os.environ["TEST_EMAIL"] = "environment@example.com"
        with self.assertLogs("send_test_email", level="INFO"):
            self.assertEqual(self.script.main([]), 0)
        self.assertEqual(
            self.connection.sendmail.call_args.args[1], ["environment@example.com"]
        )

    def test_missing_recipient_fails_before_connecting(self):
        os.environ["TEST_EMAIL"] = ""
        with self.assertLogs("send_test_email", level="ERROR"):
            self.assertEqual(self.script.main([]), 1)
        self.ssl.assert_not_called()

    def test_invalid_configuration_fails_before_connecting(self):
        os.environ["EMAIL_SMTP_PORT"] = "invalid"
        with self.assertLogs("send_test_email", level="ERROR"):
            self.assertEqual(self.script.main([]), 1)
        self.ssl.assert_not_called()

    def test_authentication_error_returns_failure(self):
        self.connection.login.side_effect = SMTPAuthenticationError(
            535, b"Invalid credentials"
        )
        with self.assertLogs("send_test_email", level="ERROR"):
            self.assertEqual(self.script.main([]), 1)
        self.connection.sendmail.assert_not_called()
        self.connection.quit.assert_called_once()

    def test_refused_recipient_returns_failure(self):
        self.connection.sendmail.return_value = {"buyer@example.com": (550, b"Refused")}
        with self.assertLogs("send_test_email", level="ERROR"):
            self.assertEqual(self.script.main([]), 1)
