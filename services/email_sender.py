import time
from smtplib import SMTPServerDisconnected

from yagmail import SMTP

from utils.log_context import redact, register_log_secret


def describe_smtp_error(error: Exception) -> str:
    code = getattr(error, "smtp_code", None)
    response = getattr(error, "smtp_error", None)
    if isinstance(response, bytes):
        response = response.decode("utf-8", errors="replace")
    details = f"SMTP {code}: {response}" if code is not None else str(error)
    return redact(f"{type(error).__name__}: {details}")


def describe_refusals(refusals: dict) -> str:
    messages = []
    for recipient, (code, response) in refusals.items():
        if isinstance(response, bytes):
            response = response.decode("utf-8", errors="replace")
        messages.append(f"{recipient}: SMTP {code}: {response}")
    return redact("; ".join(messages))


class EmailSMTP(SMTP):
    """Keep the SMTP authentication login separate from the message sender."""

    def __init__(
        self,
        *,
        smtp_login: str = "",
        diagnostic_logger=None,
        context: str = "SMTP",
        **kwargs,
    ):
        super().__init__(smtp_skip_login=True, **kwargs)
        self.smtp_login = smtp_login or self.user
        self.diagnostic_logger = (
            diagnostic_logger if diagnostic_logger is not None else self.log
        )
        self.context = context
        self.stage = "подключение"
        self.last_error = ""
        register_log_secret(kwargs.get("password", ""))

    def _login(self, password):
        # yagmail's user still controls From and the SMTP envelope sender.
        self.stage = "подключение"
        self.diagnostic_logger.info(
            "%s: подключение к SMTP %s:%s", self.context, self.host, self.port
        )
        try:
            super()._login(password)
            self.stage = "авторизация"
            self.diagnostic_logger.info("%s: SMTP подключён; авторизация", self.context)
            self.smtp.login(self.smtp_login, password)
        except Exception as error:
            self.last_error = f"этап {self.stage}: {describe_smtp_error(error)}"
            self.diagnostic_logger.error("%s: %s", self.context, self.last_error)
            raise
        self.diagnostic_logger.info("%s: SMTP-авторизация успешна", self.context)
        self.stage = "подготовка письма"

    def _attempt_send(self, recipients, msg_string):
        # Match yagmail 0.13.237's retries, delays and unsent queue, adding context.
        self.stage = "передача письма"
        self.last_error = ""
        for attempt in range(1, 4):
            self.diagnostic_logger.info(
                "%s: передача письма, попытка %d/3", self.context, attempt
            )
            try:
                result = self.smtp.sendmail(self.user, recipients, msg_string)
                self.num_mail_sent += 1
                if result:
                    self.last_error = "отказ получателя: " + describe_refusals(result)
                    self.diagnostic_logger.error(
                        "%s: %s", self.context, self.last_error
                    )
                else:
                    self.diagnostic_logger.info(
                        "%s: письмо принято SMTP-сервером", self.context
                    )
                return result
            except SMTPServerDisconnected as error:
                self.last_error = f"этап {self.stage}: {describe_smtp_error(error)}; приём письма не подтверждён"
                self.diagnostic_logger.warning(
                    "%s: попытка %d/3: %s", self.context, attempt, self.last_error
                )
                time.sleep(attempt * 3)
            except Exception as error:
                self.last_error = f"этап {self.stage}: {describe_smtp_error(error)}"
                self.diagnostic_logger.error("%s: %s", self.context, self.last_error)
                raise
        self.unsent.append((recipients, msg_string))
        self.diagnostic_logger.error(
            "%s: исчерпаны 3 попытки; %s", self.context, self.last_error
        )
        return False
