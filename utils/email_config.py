from pydantic import BaseSettings


class EmailSettings(BaseSettings):
    sender: str
    password: str
    display_name: str
    smtp_server: str = "smtp.yandex.ru"
    smtp_port: int = 465
    smtp_login: str = ""
    max_attachment_size: int = 20 * 1024 * 1024  # 20MB

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "EMAIL_"
