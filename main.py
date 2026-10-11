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
        app_logger.info("Запуск обработки заказов")

        app_settings: AppSettings = get_settings()
        app_logger.info("Настройки загружены; режим отладки: %s", app_settings.debug)
        orders_fetcher: WoocommerceFetcher = WoocommerceFetcher(
            app_logger=app_logger,
            woocommerce_settings=app_settings.woocommerce_settings,
            debug=app_settings.debug,
        )
        orders: List[Order] = orders_fetcher.fetch_orders()

        if not orders:
            app_logger.info("Нет заказов для обработки; работа завершена")
            return

        orders_handler: OrdersHandler = OrdersHandler(
            orders=orders, app_logger=app_logger, settings=app_settings
        )
        result_message: str = orders_handler.handle()
        telegram_noticifier: TelegramNoticifier = TelegramNoticifier(
            app_logger=app_logger, settings=app_settings.telegram_settings
        )
        telegram_noticifier.send_result_to_telegram(message=result_message)
        app_logger.info("Работа завершена")
    except Exception as ex:
        app_logger.exception("Обработка прервана из-за ошибки: %s", ex)


if __name__ == "__main__":
    main()
