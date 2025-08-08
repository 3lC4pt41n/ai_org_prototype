"""Basic SSRF protection helpers."""
from __future__ import annotations

import ipaddress
import socket
import urllib.parse

PRIVATE_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_url_safe(url: str) -> bool:
    """Return True if the URL is http/https and not resolving to private networks."""
    try:
        u = urllib.parse.urlparse(url)
        if u.scheme not in ("http", "https"):
            return False
        host = u.hostname
        if not host:
            return False
        for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if any(ip in net for net in PRIVATE_NETS):
                return False
        return True
    except Exception:  # pragma: no cover - defensive
        return False
