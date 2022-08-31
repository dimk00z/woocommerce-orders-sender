import logging.config
from typing import List

from models.order import Order
from services.orders_handler import OrdersHandler
from services.telegram_noticifier import TelegramNoticifier
from services.woocommerce_fetcher import WoocommerceFetcher
from utils.config import AppSettings, get_settings
from utils.logger import logger_config

app_logger = logging.getLogger("app_logger")


def main():
    try:
        logging.config.dictConfig(logger_config)

        app_settings: AppSettings = get_settings()
        orders_fetcher: WoocommerceFetcher = WoocommerceFetcher(
            app_logger=app_logger,
            woocommerce_settings=app_settings.woocommerce_settings,
        )
        orders: List[Order] = orders_fetcher.fetch_orders()

        if not orders:
            return

        orders_handler: OrdersHandler = OrdersHandler(
            orders=orders, app_logger=app_logger, settings=app_settings
        )
        result_message: str = orders_handler.handle()
        telegram_noticifier: TelegramNoticifier = TelegramNoticifier(
            app_logger=app_logger, settings=app_settings.telegram_settings
        )
        telegram_noticifier.send_result_to_telegram(message=result_message)
    except:
        app_logger.exception("Everything is bad:")


if __name__ == "__main__":
    main()
