from typing import List

import requests
from models.proxy import Proxy


class ProxyLoader:
    """Load free proxies from proxifly all-list, ordered by protocol priority."""

    URL = (
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list"
        "@main/proxies/all/data.json"
    )
    # socks5 first, then http; https/socks4 skipped
    PROTOCOL_PRIORITY = {
        "socks5": 0,
        "http": 1,
    }

    def __init__(self) -> None:
        self.proxies: List[Proxy] = []

    def act(self) -> List[Proxy]:
        """Fetch all proxies and sort: socks5 → http, then by score."""
        if self.proxies:
            return self.proxies
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
            print(f"Loaded {len(self.proxies)} proxies")
        except Exception as ex:
            print(f"Failed to load proxies: {ex}")
            self.proxies = []
        return self.proxies
