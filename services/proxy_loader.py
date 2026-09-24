from pathlib import Path
from typing import List, Optional

import requests
from models.proxy import Proxy


class ProxyLoader:
    """Load free US proxies from proxifly, ordered by protocol priority."""

    URL = (
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list"
        "@main/proxies/countries/US/data.json"
    )
    LAST_PROXY_PATH = Path(__file__).resolve().parent.parent / ".last_proxy"
    # http first, then socks5; https/socks4 skipped
    PROTOCOL_PRIORITY = {
        "http": 0,
        "socks5": 1,
    }

    def __init__(self) -> None:
        self.proxies: List[Proxy] = []

    def get_last_success(self) -> Optional[str]:
        try:
            value = self.LAST_PROXY_PATH.read_text(encoding="utf-8").strip()
            return value or None
        except OSError:
            return None

    def save_last_success(self, proxy_url: str) -> None:
        if not proxy_url:
            return
        try:
            self.LAST_PROXY_PATH.write_text(proxy_url + "\n", encoding="utf-8")
        except OSError as ex:
            print(f"Failed to save last proxy: {ex}")

    def candidates(self, *, configured: str = "", limit: int = 30) -> List[str]:
        """Build proxy list: last success → configured → loaded list."""
        result: List[str] = []

        last = self.get_last_success()
        if last:
            result.append(last)
            print(f"Using cached last proxy first: {last}")

        if configured and configured not in result:
            result.append(configured)

        for proxy in self.act():
            if proxy.proxy and proxy.proxy not in result:
                result.append(proxy.proxy)
            if len(result) >= limit:
                break

        if not result:
            result.append("")
        return result

    def act(self) -> List[Proxy]:
        """Fetch US proxies and sort by protocol priority, then by score."""
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
