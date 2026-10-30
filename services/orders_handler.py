import logging
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from smtplib import (
    SMTPException,
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
from yagmail.error import YagAddressError, YagConnectionClosed, YagInvalidEmailAddress

from models.order import Order, Product, ProductFile
from services.coupon_creater import Coupon, CouponCreater
from services.email_sender import EmailSMTP, describe_smtp_error
from utils.config import AppSettings
from utils.http import HEADERS
from utils.log_context import current_run_id, redact

EMAIL_SENDING_ERRORS = (
    OSError,
    SMTPException,
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


@dataclass
class EmailOutcome:
    part: int
    total: int
    accepted: bool
    details: str


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
        self.run_id = current_run_id()
        self.email_results: Dict[str, List[EmailOutcome]] = {}
        self.order_errors: Dict[str, str] = {}
        self.order_status_results: Dict[str, str] = {}

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
            self.app_logger.debug("Заказ №%s: купон не требуется", order.id)
            return

        self.app_logger.info("Заказ №%s: подготовка купона", order.id)
        coupon: Coupon | None = CouponCreater(
            total=order.total,
            name=order.first_name,
            settings=self.settings.woocommerce_settings,
        )()
        if coupon is None:
            self.app_logger.debug(
                "Заказ №%s: купон не предусмотрен для этой суммы", order.id
            )
            return
        self.app_logger.info(
            "Заказ №%s: купон создан, скидка %s%%", order.id, coupon.discount_percent
        )

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
        self.app_logger.info(
            "Заказ №%s: подготовка письма, вложений %d",
            order.id,
            len(order.total_files),
        )
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
                order_id=order.id,
                attachment_bytes=sum(file.file_size for file in order.total_files),
            )
        # Splitted logic
        splitted_files: List[List[str]] = OrdersHandler._split_files(
            files=order.total_files,
            max_attachment_size=self.settings.email_settings.max_attachment_size,
        )
        results: List[bool] = []
        self.app_logger.info(
            "Заказ №%s: вложения разделены на %d писем", order.id, len(splitted_files)
        )
        for pack_index, file_pack in enumerate(splitted_files):
            self.app_logger.info(
                "Заказ №%s: отправка части %d/%d",
                order.id,
                pack_index + 1,
                len(splitted_files),
            )
            results.append(
                self._send_email(
                    to_email=order.email,
                    subject=f"Заказ №{order.id} - часть {pack_index + 1}",
                    contents=[template.render(**order_info)],
                    attachments=file_pack,
                    order_id=order.id,
                    part_number=pack_index + 1,
                    parts_count=len(splitted_files),
                    attachment_bytes=sum(
                        file.file_size
                        for file in order.total_files
                        if file.file_name in file_pack
                    ),
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
        order_id: str = None,
        part_number: int = 1,
        parts_count: int = 1,
        attachment_bytes: int = 0,
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
        context = (
            f"Заказ №{order_id}, часть {part_number}/{parts_count}"
            if order_id is not None
            else f"Письмо {subject!r}"
        )

        def finish(accepted: bool, details: str) -> bool:
            details = redact(details)
            if order_id is not None:
                self.email_results.setdefault(order_id, []).append(
                    EmailOutcome(part_number, parts_count, accepted, details)
                )
            return accepted

        yag = None
        try:
            email_settings = self.settings.email_settings
            self.app_logger.info(
                "%s: получатель %s, вложений %d, размер %d байт, SMTP %s:%s",
                context,
                to_email,
                len(attachments),
                attachment_bytes,
                email_settings.smtp_server,
                email_settings.smtp_port,
            )

            with EmailSMTP(
                user={email_settings.sender: email_settings.display_name},
                smtp_login=email_settings.smtp_login,
                diagnostic_logger=self.app_logger,
                context=context,
                password=email_settings.password,
                smtp_ssl=True,
                host=email_settings.smtp_server,
                port=int(email_settings.smtp_port),
            ) as yag:
                result = yag.send(
                    to=to_email,
                    subject=subject,
                    contents=contents,
                    attachments=attachments,
                )
            if result is False or result:
                reason = (
                    yag.last_error
                    or "SMTP вернул неуспешный результат; приём письма не подтверждён"
                )
                self.app_logger.error(
                    "%s для %s: %s",
                    context,
                    to_email,
                    reason,
                )
                return finish(False, reason)
            self.app_logger.info(
                "Письмо %r для %s принято SMTP-сервером", subject, to_email
            )
            return finish(True, "принято SMTP-сервером")

        except EMAIL_SENDING_ERRORS as ex:
            reason = (
                yag.last_error
                if yag and yag.last_error
                else (
                    f"этап {yag.stage if yag else 'подготовка SMTP'}: {describe_smtp_error(ex)}"
                )
            )
            self.app_logger.exception(
                "%s для %s: %s",
                context,
                to_email,
                reason,
            )
            return finish(False, reason)

    def _handle_order(self, *, order: Order) -> bool:
        """Send email and change status if email is ok

        Args:
            order (Order): _description_

        Returns:
            bool: _description_
        """

        if self._send_order_email(order=order):
            self.app_logger.info("Заказ №%s: все письма отправлены", order.id)
            return self._close_order(order=order)

        self.app_logger.error(
            "Заказ №%s: отправка писем не завершена; изменение статуса WooCommerce не запрашивалось",
            order.id,
        )
        return False

    def _close_order(self, *, order: Order) -> bool:
        """Close woocommerce order

        Args:
            order (Order): _description_
        """
        try:
            self.app_logger.info("Заказ №%s: изменение статуса на completed", order.id)
            put_url = f"{self.settings.woocommerce_settings.url}/orders/{order.id}"
            session = requests.Session()
            session.headers = HEADERS
            self.order_status_results[
                order.id
            ] = "изменение статуса WooCommerce запрошено, но результат не подтверждён"
            r = session.put(
                put_url, auth=self.auth_pair, params={"status": "completed"}
            )
            if r.status_code == HTTPStatus.OK:
                self.app_logger.info("Заказ №%s: статус изменён на completed", order.id)
                return True
            self.app_logger.error(
                "Заказ №%s: письмо принято SMTP, изменение статуса не подтверждено; HTTP %s",
                order.id,
                r.status_code,
            )
            self.order_errors[
                order.id
            ] = f"Письма приняты SMTP, изменение статуса WooCommerce не подтверждено: HTTP {r.status_code}"
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as error:
            self.order_errors[
                order.id
            ] = f"Письма приняты SMTP, ошибка изменения статуса: {type(error).__name__}: {error}"
            self.app_logger.exception("Заказ №%s: ошибка изменения статуса", order.id)

        return False

    def _create_result_message(self) -> str:
        """Create result handle meassage

        Returns:
            str: _description_
        """

        def safe(value) -> str:
            return escape(redact(str(value)), quote=False)

        message_lines: List[str] = [f"Итог запуска {safe(self.run_id)}"]
        total: float = 0.0
        bad_orders = []
        for order in self.orders:
            if order.status is False:
                bad_orders.append(order)
            else:
                products = "\n".join(
                    [f" · <b>{safe(product.name)}</b>" for product in order.products]
                )
                message_lines.append(
                    safe(
                        f"№ {order.id} - {order.first_name} {order.last_name}, {order.email}"
                    )
                    + f"\n{products}\n<b>{safe(order.total)} руб.</b>"
                )
                total += order.total
            if not order.status:
                message_lines.append(safe(f"Ошибка заказа №{order.id} — {order.email}"))
            for result in self.email_results.get(order.id, []):
                message_lines.append(
                    safe(
                        f"Заказ №{order.id}, часть {result.part}/{result.total}: {result.details}"
                    )
                )
            status_result = (
                "все письма приняты SMTP; статус WooCommerce подтверждён: completed"
                if order.status
                else self.order_status_results.get(
                    order.id, "изменение статуса WooCommerce не запрашивалось"
                )
            )
            message_lines.append(safe(f"Заказ №{order.id}: {status_result}"))
            if order.id in self.order_errors:
                message_lines.append(safe(self.order_errors[order.id]))
            elif not order.status and not self.email_results.get(order.id):
                message_lines.append(
                    "Обработка не завершена; подробности в логах заказа"
                )
        message_lines.append(
            f"Всего {len(self.orders)}, успешно {len(self.orders) - len(bad_orders)}, "
            f"с ошибками {len(bad_orders)}.\n\n<b>Сумма успешных заказов: {total} руб.</b>"
        )
        return "\n".join(message_lines)

    def handle(self, *, timeout=45) -> str:
        self.app_logger.info("Начало обработки %d заказов", len(self.orders))
        for order_index, order in enumerate(self.orders):
            self.app_logger.info(
                "Заказ №%s (%d/%d): начало обработки",
                order.id,
                order_index + 1,
                len(self.orders),
            )
            try:
                self.orders[order_index].status = self._handle_order(order=order)
            except Exception as error:
                self.orders[order_index].status = False
                self.order_errors[order.id] = redact(
                    f"Ошибка обработки: {type(error).__name__}: {error}"
                )
                self.app_logger.exception("Заказ №%s: ошибка обработки", order.id)
            self.app_logger.info(
                "Заказ №%s: результат обработки — %s",
                order.id,
                "успешно" if order.status else "ошибка",
            )
            if order_index + 1 == len(self.orders):
                break
            self.app_logger.debug("Пауза перед следующим заказом: %s секунд", timeout)
            sleep(timeout)
        successful = sum(order.status for order in self.orders)
        self.app_logger.info(
            "Обработка завершена: всего %d, успешно %d, с ошибками %d",
            len(self.orders),
            successful,
            len(self.orders) - successful,
        )
        return self._create_result_message()
