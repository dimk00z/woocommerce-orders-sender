import logging
from typing import List

import requests
from models.proxy import Proxy


class ProxyLoader:
    """Load free proxies from proxifly all-list, ordered by protocol priority."""

    URL = (
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list"
        "@main/proxies/all/data.json"
    )
    # https first, then socks5, then http; socks4 skipped
    PROTOCOL_PRIORITY = {
        "https": 0,
        "socks5": 1,
        "http": 2,
    }

    def __init__(self, *, app_logger: logging.Logger) -> None:
        self.app_logger = app_logger
        self.proxies: List[Proxy] = []

    def act(self) -> List[Proxy]:
        """Fetch all proxies and sort: https → socks5 → http, then by score."""
        try:
            response = requests.get(self.URL, timeout=30)
            response.raise_for_status()
            proxies = [Proxy.parse_obj(item) for item in response.json()]
            proxies = [
                p for p in proxies if p.protocol in self.PROTOCOL_PRIORITY
            ]
            proxies.sort(
                key=lambda p: (
                    self.PROTOCOL_PRIORITY[p.protocol],
                    -p.score,
                )
            )
            self.proxies = proxies
            self.app_logger.info("Loaded %s proxies", len(self.proxies))
        except Exception as ex:
            self.app_logger.exception("Failed to load proxies: %s", ex)
            self.proxies = []
        return self.proxies
