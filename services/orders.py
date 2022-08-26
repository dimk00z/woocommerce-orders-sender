import logging
from typing import Any, List, Optional, Tuple

import requests
from models.order import Order, Product
from utils.config import WoocommerceSettings

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "dnt": "1",
    "pragma": "no-cache",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36",
}


class WoocommerceFetcher:
    def _parse_orders(self, wc_processing_orders) -> List[Order]:
        orders: List[Order] = []
        for order_info in wc_processing_orders:
            order: Order = Order(
                id=order_info["id"],
                total=order_info["total"],
                email=order_info["billing"]["email"],
                first_name=order_info["billing"]["first_name"],
                last_name=order_info["billing"]["last_name"],
            )
            for product in order_info["line_items"]:
                product_url = f'{self.url}/products/{product["product_id"]}'
                product_info = self._fetch_wc_url(self.auth_pair, product_url)
                # TODO here
        return orders

    def __init__(self, woocommerce_settings: WoocommerceSettings, app_logger: logging.Logger) -> None:
        self.auth_pair: Tuple[str, str] = (woocommerce_settings.user_key, woocommerce_settings.secret_key)
        self.url = f"{woocommerce_settings.url}/wp-json/wc/v3"
        self.logger = app_logger

    def _fetch_wc_url(self, url, params={}) -> Optional[Any]:
        try:
            session = requests.Session()
            session.headers = HEADERS
            r = session.get(url, auth=self.auth_pair, params=params)
            return r.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
            self.logger.exception(f"Something bad: {error}")
            return None

    def fetch_orders(self) -> List[Order]:
        orders: List[Order] = []
        orders_url = f"{self.url}/orders"
        params = {"status": "processing"}
        wc_processing_orders = self._fetch_wc_url(orders_url, params)
        if wc_processing_orders:
            orders = WoocommerceFetcher._parse_orders(wc_processing_orders)
        return orders
