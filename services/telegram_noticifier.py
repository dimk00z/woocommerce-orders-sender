import logging
from typing import List

import telebot
from models.order import Order
from utils.config import TelegramSettrings


class TelegramNoticifier:
    def __init__(self, *, settings: TelegramSettrings, app_logger: logging.Logger) -> None:
        self.settings: TelegramSettrings = settings
        self.app_logger: logging.Logger = app_logger
        self.bot = telebot.TeleBot(self.settings.bot_token)

    def _create_result_message(self, *, orders: List[Order]) -> str:
        message = ""
        total = 0.0
        bad_orders = []

        message = "Обработано:\n"
        # TODO Update logic here

        for order in orders:
            products = ", ".join(
                [product_info["name"] for product_id, product_info in order["products"].items()]
            )
            message += f'Заказ №{order["id"]} ({products}) на {order["total"]} руб. \n'
            total += float(order["total"])
            if order["status"] == False:
                bad_orders.append(order)
        if len(orders) > 1:
            message += f"Всего {len(orders)} заказов на {total} руб."
        if bad_orders:
            bad_orders_id = [bad_order["id"] for bad_order in bad_orders]
            message = f"{message}\nОшибки: {bad_orders_id}"
        return message

    def send_result_to_telegram(self, *, orders):
        message = self._create_result_message(orders)
        for user in self.settings.telegram_users:
            if user:
                self.bot.send_message(user, message)
