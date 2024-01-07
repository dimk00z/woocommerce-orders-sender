import re
from dataclasses import dataclass
from datetime import date, timedelta
from sys import maxsize
from uuid import uuid4

import backoff
import requests
from transliterate import translit

from utils.config import WoocommerceSettings
from utils.http import HEADERS

COUPON_DAYS: int = 7


@dataclass(frozen=True, slots=True)
class CouponeDiscount:
    min_total: float | int
    max_total: float | int
    discount_percent: int


COUPONE_DICSOUNT: tuple[CouponeDiscount, ...] = (
    CouponeDiscount(
        min_total=10,
        max_total=1499,
        discount_percent=5,
    ),
    CouponeDiscount(
        min_total=1500,
        max_total=2499,
        discount_percent=10,
    ),
    CouponeDiscount(
        min_total=2500,
        max_total=3499,
        discount_percent=15,
    ),
    CouponeDiscount(
        min_total=3500,
        max_total=maxsize,
        discount_percent=20,
    ),
)


@dataclass(
    frozen=True,
    slots=True,
)
class Coupon:
    coupon_name: str
    discount_percent: int | float
    days: int = COUPON_DAYS


@dataclass
class CouponCreater:
    total: int | float
    name: str
    settings: WoocommerceSettings
    days: int = COUPON_DAYS

    def __call__(self) -> Coupon | None:
        return self._get_coupon(
            total=self.total,
            name=self.name,
        )

    def _get_coupon(
        self,
        total: int | float,
        name: str,
    ) -> Coupon | None:
        discount_percent = self._get_discount_percent(total=total)
        if discount_percent == 0:
            return None

        coupon_name = self._get_coupon_name(name=name)
        days = self.days
        coupone: Coupon = Coupon(
            coupon_name=coupon_name,
            discount_percent=discount_percent,
            days=days,
        )
        self._upload_coupone(coupone=coupone)

        return coupone

    def _get_coupon_name(
        self,
        name: str,
        pattern: str = "[^A-Za-z0-9_]+",
    ) -> str:
        first_name_part = translit(
            "_".join(name.split()),
            "ru",
            reversed=True,
        )
        second_name_part = str(uuid4()).split("-")[0]
        coupon_name = f"{first_name_part}_{second_name_part}"
        return str(re.sub(pattern, "", coupon_name.lower()))

    def _get_discount_percent(
        self,
        total: int | float,
    ) -> int:
        for discount in COUPONE_DICSOUNT:
            if total >= discount.min_total and total <= discount.max_total:
                return discount.discount_percent
        return 0

    def _count_date_expires(
        self,
    ) -> str:
        end_date = date.today() + timedelta(days=self.days)
        return end_date.strftime("%Y-%m-%d")

    @backoff.on_exception(
        backoff.expo,
        requests.exceptions.RequestException,
        raise_on_giveup=True,
        max_tries=3,
    )
    def _upload_coupone(self, coupone: Coupon) -> None:
        auth_pair = (self.settings.user_key, self.settings.secret_key)
        url = f"{self.settings.url}/coupons"
        with requests.Session() as session:
            session.headers = HEADERS
            response = session.post(
                url,
                auth=auth_pair,
                params={
                    "code": coupone.coupon_name,
                    "discount_type": "percent",
                    "amount": coupone.discount_percent,
                    "date_expires": self._count_date_expires(),
                    "individual_use": True,
                    "usage_limit": "1",
                },
            )
            response.raise_for_status()
