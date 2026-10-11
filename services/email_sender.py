from yagmail import SMTP


class EmailSMTP(SMTP):
    """Keep the SMTP authentication login separate from the message sender."""

    def __init__(self, *, smtp_login: str = "", **kwargs):
        super().__init__(smtp_skip_login=True, **kwargs)
        self.smtp_login = smtp_login or self.user

    def _login(self, password):
        # yagmail's user still controls From and the SMTP envelope sender.
        super()._login(password)
        self.smtp.login(self.smtp_login, password)
