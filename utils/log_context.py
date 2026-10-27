"""Context shared by console logs, Telegram logs and order reports."""

import logging
import re
from contextvars import ContextVar
from uuid import uuid4

_run_id = ContextVar("run_id", default="-")
_secrets = ContextVar("log_secrets", default=())


def start_run() -> str:
    run_id = uuid4().hex[:12]
    _run_id.set(run_id)
    return run_id


def current_run_id() -> str:
    return _run_id.get()


def register_log_secret(value: str) -> None:
    if value and value not in _secrets.get():
        _secrets.set((*_secrets.get(), value))


def redact(text: str) -> str:
    for value in sorted(_secrets.get(), key=len, reverse=True):
        text = text.replace(value, "***")
    return re.sub(r"/bot[^/\s?]+", "/bot***", text)


class RunContextFilter(logging.Filter):
    def filter(self, record):
        record.run_id = current_run_id()
        return True


class TelegramLogFilter(RunContextFilter):
    def filter(self, record):
        return super().filter(record) and not getattr(record, "console_only", False)


class SafeFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))
