import logging
from pathlib import Path
from typing import List, Set, Tuple

import requests
from models.order import Order, Product, ProductFile
from requests.exceptions import HTTPError
from utils.config import WoocommerceSettings
from utils.http import HEADERS


class WoocommerceFetcher:
    """Class for fetching orders from woocommerce rest api"""

    def __init__(
        self,
        *,
        woocommerce_settings: WoocommerceSettings,
        app_logger: logging.Logger,
        debug: bool = False,
    ) -> None:
        self.auth_pair: Tuple[str, str] = (
            woocommerce_settings.user_key,
            woocommerce_settings.secret_key,
        )
        self.url = woocommerce_settings.url
        self.logger = app_logger
        self.debug = debug
        self.redundant_phrase: str = woocommerce_settings.redundant_phrase
        if self.debug:
            self.debug_email: str = woocommerce_settings.debug_email

    def _sanitaze_order_name(self, *, order_name) -> str:
        """Simple sanitize func

        Args:
            order_name (_type_): _description_

        Returns:
            str: _description_
        """
        return order_name.replace(self.redundant_phrase, "")

    def _parse_orders(self, *, wc_processing_orders) -> List[Order]:
        """Get orders with processing status

        Args:
            wc_processing_orders (_type_): _description_

        Returns:
            List[Order]: _description_
        """
        orders: List[Order] = []
        for order_info in wc_processing_orders:
            self.logger.info("Подготовка заказа №%s", order_info["id"])
            order: Order = Order(
                id=order_info["id"],
                total=order_info["total"],
                email=order_info["billing"]["email"],
                first_name=order_info["billing"]["first_name"],
                last_name=order_info["billing"]["last_name"],
            )
            total_files: Set[str] = set()
            for product in order_info["line_items"]:
                product_url = f"{self.url}/products/{product['product_id']}"
                self.logger.debug(
                    "Заказ №%s: загрузка товара №%s", order.id, product["product_id"]
                )
                product_info = self._fetch_wc_url(url=product_url)
                fetched_product: Product = Product(
                    name=self._sanitaze_order_name(order_name=product["name"]),
                    purchase_note=product_info["purchase_note"]
                    if "purchase_note" in product_info
                    else "",
                )

                if "downloads" in product_info:
                    for file in product_info["downloads"]:
                        total_files.add(file["file"])
                order.products.append(fetched_product)
            order.total_files = [
                ProductFile(
                    file_name=file_name, file_size=Path(file_name).stat().st_size
                )
                for file_name in total_files
            ]
            orders.append(order)
            self.logger.info(
                "Заказ №%s подготовлен: товаров %d, файлов %d, размер %d байт",
                order.id,
                len(order.products),
                len(order.total_files),
                sum(file.file_size for file in order.total_files),
            )
        return orders

    def _fetch_wc_url(self, *, url, params={}):
        """Fetch woocommerce API

        Args:
            url (_type_): _description_
            params (dict, optional): _description_. Defaults to {}.

        Returns:
            _type_: _description_
        """
        try:
            self.logger.debug("Запрос WooCommerce: %s", url)
            session = requests.Session()
            session.headers = HEADERS
            r = session.get(url, auth=self.auth_pair, params=params)
            r.raise_for_status()
            self.logger.debug("Ответ WooCommerce: HTTP %s", r.status_code)

            if r is None:
                raise HTTPError

            return r.json()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            HTTPError,
        ) as error:
            self.logger.exception("Ошибка запроса WooCommerce %s: %s", url, error)
            return None

    def fetch_orders(self) -> List[Order]:
        """Main entart point for class

        Returns:
            List[Order]: _description_
        """
        orders: List[Order] = []
        self.logger.info("Загрузка заказов WooCommerce со статусом processing")
        orders_url = f"{self.url}/orders"
        params = {"status": "processing"}
        response = self._fetch_wc_url(url=orders_url, params=params)
        if response is None:
            self.logger.error("Не удалось загрузить заказы WooCommerce")
            raise RuntimeError("Загрузка заказов WooCommerce не выполнена")
        self.logger.info("Загружено заказов: %d", len(response))
        if response:
            orders = self._parse_orders(wc_processing_orders=response)
        if self.debug:
            orders = [order for order in orders if order.email == self.debug_email]
            self.logger.info("После фильтра отладки осталось заказов: %d", len(orders))
        self.logger.info("Готово к обработке заказов: %d", len(orders))
        return orders
