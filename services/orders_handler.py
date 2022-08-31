import logging
import smtplib
from http import HTTPStatus
from time import sleep
from typing import Dict, List, Tuple

import binpacking
import requests
import yagmail
from jinja2 import Template
from models.order import Order, ProductFile
from utils.config import AppSettings
from utils.http import HEADERS
from yagmail.error import YagAddressError, YagConnectionClosed, YagInvalidEmailAddress


class OrdersHandler:
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

    def _send_order_email(self, *, order: Order) -> bool:
        """Create email message and send it

        Args:
            order (Order): _description_

        Returns:
            bool: _description_
        """
        email_lines: List[str] = ['<p><b color="blue">Вы приобрели:</b></p><ul>']
        for product in order.products:
            product_description = f"<p>{product.purchase_note}</p>" if product.purchase_note else ""
            email_lines.append(f'<li><p><b color="blue">{product.name}</b></p>{product_description}</li>')
        email_lines.append('</ul><hr style="border-bottom: 0px">')
        email_message: str = "".join(email_lines)
        order_info: Dict[str, str] = {
            "first_name": order.first_name,
            "last_name": order.last_name,
            "id": order.id,
            "email_message": email_message,
        }
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
            files=order.total_files, max_attachment_size=self.settings.email_settings.max_attachment_size
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

    @staticmethod
    def _split_files(
        *, files: List[ProductFile], max_attachment_size: int, maximum_filling: float = 0.8
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

    def _send_email(self, *, to_email: str, subject: str, attachments: List[str], contents) -> bool:
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

            yag = yagmail.SMTP(
                user={email_settings.sender: email_settings.display_name},
                password=email_settings.password,
                smtp_ssl=True,
                host=email_settings.smtp_server,
                port=int(email_settings.smtp_port),
            )
            yag.send(to=to_email, subject=subject, contents=contents, attachments=attachments)
            return True

        except (
            YagInvalidEmailAddress,
            YagConnectionClosed,
            smtplib.SMTPAuthenticationError,
            YagAddressError,
            smtplib.SMTPDataError,
            smtplib.SMTPServerDisconnected,
        ) as ex:
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
            r = session.put(put_url, auth=self.auth_pair, params={"status": "completed"})
            if r.status_code == HTTPStatus.OK:
                return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
            self.app_logger.exception("Something bad:")

        return False

    def _create_result_message(self) -> str:
        """Create result handle meassage

        Returns:
            str: _description_
        """
        message: str = ""
        total: float = 0.0
        bad_orders = []
        for order in self.orders:
            if order.status is False:
                bad_orders.append(order)
                continue
            products = "\n".join([f"· {product.name}" for product in order.products])
            message += f"№ {order.id} - {order.first_name} {order.last_name}, {order.email} на **{order.total} руб.**\n {products}"
            total += order.total
        if len(self.orders) > 1:
            message += f"Всего {len(self.orders)} заказов на **{total} руб.**"
        if bad_orders:
            errors: List[str] = [f"{bad_order.id} - {bad_order.email}" for bad_order in bad_orders]
            message = f"{message}\nОшибки: {errors}"
        return message

    def handle(self, *, timeout=45) -> str:
        for order_index, order in enumerate(self.orders):
            self.orders[order_index].status = self._handle_order(order=order)
            if order_index + 1 == len(self.orders):
                break
            sleep(timeout)
        return self._create_result_message()
