import logging
from http import HTTPStatus
from smtplib import (
    SMTPAuthenticationError,
    SMTPDataError,
    SMTPSenderRefused,
    SMTPServerDisconnected,
)
from time import sleep
from typing import Dict, List, Tuple

import binpacking
import requests
from jinja2 import Template
from yagmail import SMTP
from yagmail.error import YagAddressError, YagConnectionClosed, YagInvalidEmailAddress

from models.order import Order, Product, ProductFile
from services.coupon_creater import Coupon, CouponCreater
from utils.config import AppSettings
from utils.http import HEADERS

EMAIL_SENDING_ERRORS = (
    YagInvalidEmailAddress,
    YagConnectionClosed,
    SMTPAuthenticationError,
    YagAddressError,
    SMTPDataError,
    SMTPServerDisconnected,
    SMTPSenderRefused,
)

PRODUCTS_WITHOUT_COUPON: List[str] = [
    "оплата занятий",
]


class OrdersHandler:
    """Class for orders logic
    sending emails
    changing orders statuses
    noticify results to telegram"""

    def __init__(
        self,
        *,
        orders: List[Order],
        settings: AppSettings,
        app_logger: logging.Logger,
        email_template: str = "email_template.html",
    ) -> None:
        self.orders: List[Order] = orders
        self.settings: AppSettings = settings
        self.app_logger: logging.Logger = app_logger
        self.auth_pair: Tuple[str, str] = (
            settings.woocommerce_settings.user_key,
            settings.woocommerce_settings.secret_key,
        )
        self.email_template = email_template

    def _get_order_info(self, *, order: Order) -> Dict[str, str]:
        email_lines: List[str] = ['<p><b color="blue">Состав заказа:</b></p><ul>']
        for product in order.products:
            product_description = (
                f"<p>{product.purchase_note}</p>" if product.purchase_note else ""
            )
            email_lines.append(
                f'<li><p><b color="blue">{product.name}</b></p>{product_description}</li>'
            )
        email_lines.append('</ul><hr style="border-bottom: 0px">')

        self._add_coupon_if_order_ok(order, email_lines)

        email_message: str = "".join(email_lines)
        return {
            "first_name": order.first_name,
            "last_name": order.last_name,
            "id": order.id,
            "email_message": email_message,
        }

    def _check_products_for_discount(self, order: Order) -> bool:
        products_without_discount: List[Product] = []

        for product in order.products:
            if product in products_without_discount:
                continue
            for skip_product_name in PRODUCTS_WITHOUT_COUPON:
                if skip_product_name in product.name.lower():
                    products_without_discount.append(product)
                    break

        return len(products_without_discount) == len(order.products)

    def _add_coupon_if_order_ok(
        self,
        order: Order,
        email_lines: List[str],
    ):
        if order.total <= 0 or self._check_products_for_discount(order):
            return

        coupon: Coupon | None = CouponCreater(
            total=order.total,
            name=order.first_name,
            settings=self.settings.woocommerce_settings,
        )()
        if coupon is None:
            return

        email_lines.append(
            "".join(
                (
                    "<p>",
                    f"""Хочу поблагодарить вас за выбор моих материалов скидкой <b>{coupon.discount_percent} %</b>.<br />Вводите на сайте ваш промокод <b>{coupon.coupon_name}</b> и покупайте с выгодой!<br />
                Он будет действовать в течение недели со дня этой покупки""",
                    "</p>",
                    '<hr style="border-bottom: 0px">',
                )
            )
        )

    @staticmethod
    def _split_files(
        *,
        files: List[ProductFile],
        max_attachment_size: int,
        maximum_filling: float = 0.8,
    ) -> List[List[str]]:
        """Split list of files by max capacity

        Args:
            files (List[ProductFile]): _description_
            max_attachment_size (int): _description_
            maximum_filling (float, optional): _description_. Defaults to 0.8.

        Returns:
            List[List[str]]: _description_
        """

        bins = binpacking.to_constant_volume(
            d={file.file_name: file.file_size for file in files},
            V_max=int(max_attachment_size * maximum_filling),
        )
        return [[file_name for file_name in bin] for bin in bins]

    def _send_order_email(self, *, order: Order) -> bool:
        """Create email message and send it

        Args:
            order (Order): _description_

        Returns:
            bool: _description_
        """
        order_info: Dict[str, str] = self._get_order_info(order=order)
        with open("email_template.html", "rb") as f:
            html = f.read().decode("UTF-8")
        template: Template = Template(html)

        if (
            sum((file.file_size for file in order.total_files))
            <= self.settings.email_settings.max_attachment_size
        ):
            return self._send_email(
                to_email=order.email,
                subject=f"Заказ №{order.id}",
                contents=[template.render(**order_info)],
                attachments=[file.file_name for file in order.total_files],
            )
        # Splitted logic
        splitted_files: List[List[str]] = OrdersHandler._split_files(
            files=order.total_files,
            max_attachment_size=self.settings.email_settings.max_attachment_size,
        )
        results: List[bool] = []
        for pack_index, file_pack in enumerate(splitted_files):
            results.append(
                self._send_email(
                    to_email=order.email,
                    subject=f"Заказ №{order.id} - часть {pack_index+1}",
                    contents=[template.render(**order_info)],
                    attachments=file_pack,
                )
            )
        return all(results)

    def _send_email(
        self,
        *,
        to_email: str,
        subject: str,
        attachments: List[str],
        contents,
    ) -> bool:
        """Send email with yagmail

        Args:
            to_email (str): _description_
            subject (str): _description_
            attachments (List[str]): _description_
            contents (_type_): _description_

        Returns:
            bool: _description_
        """
        try:
            email_settings = self.settings.email_settings

            yag = SMTP(
                user={email_settings.sender: email_settings.display_name},
                password=email_settings.password,
                smtp_ssl=True,
                host=email_settings.smtp_server,
                port=int(email_settings.smtp_port),
            )
            yag.send(
                to=to_email,
                subject=subject,
                contents=contents,
                attachments=attachments,
            )
            return True

        except EMAIL_SENDING_ERRORS as ex:
            self.app_logger.exception(f"Everything is bad:{ex}")
            return False

    def _handle_order(self, *, order: Order) -> bool:
        """Send email and change status if email is ok

        Args:
            order (Order): _description_

        Returns:
            bool: _description_
        """

        if self._send_order_email(order=order):
            return self._close_order(order=order)

        return False

    def _close_order(self, *, order: Order) -> bool:
        """Close woocommerce order

        Args:
            order (Order): _description_
        """
        try:
            put_url = f"{self.settings.woocommerce_settings.url}/orders/{order.id}"
            session = requests.Session()
            session.headers = HEADERS
            r = session.put(
                put_url, auth=self.auth_pair, params={"status": "completed"}
            )
            if r.status_code == HTTPStatus.OK:
                return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            self.app_logger.exception("Something bad:")

        return False

    def _create_result_message(self) -> str:
        """Create result handle meassage

        Returns:
            str: _description_
        """
        message_lines: List[str] = []
        total: float = 0.0
        bad_orders = []
        for order in self.orders:
            if order.status is False:
                bad_orders.append(order)
                continue
            products = "\n".join([f" · {product.name}" for product in order.products])
            message_lines.append(
                f"№ {order.id} - {order.first_name} {order.last_name}, {order.email}\n{products}\n{order.total} руб."
            )
            total += order.total
        if len(self.orders) > 1:
            message_lines.append(f"Всего {len(self.orders)} заказов на {total} руб.")
        if bad_orders:
            message_lines.append("Ошибки:")
            message_lines.append(
                ", ".join(
                    [f"{bad_order.id} - {bad_order.email}" for bad_order in bad_orders]
                )
            )
        return "\n".join(message_lines)

    def handle(self, *, timeout=45) -> str:
        for order_index, order in enumerate(self.orders):
            self.orders[order_index].status = self._handle_order(order=order)
            if order_index + 1 == len(self.orders):
                break
            sleep(timeout)
        return self._create_result_message()
