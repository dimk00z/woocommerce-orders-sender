from typing import Optional

from pydantic import BaseModel


class ProxyGeolocation(BaseModel):
    country: str = ""
    city: str = ""


class Proxy(BaseModel):
    proxy: str
    protocol: str = "http"
    ip: str = ""
    port: int = 0
    https: bool = False
    anonymity: str = ""
    score: int = 0
    geolocation: Optional[ProxyGeolocation] = None
