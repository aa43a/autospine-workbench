"""Loopback host and origin checks shared by the local HTTP boundary."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def is_loopback_host(host: str) -> bool:
    candidate = host.strip().lower()
    if candidate == "localhost":
        return True
    if "%" in candidate:
        candidate = candidate.split("%", 1)[0]
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def host_header_is_local(value: str | None) -> bool:
    if not value:
        return True  # HTTP/1.0 clients need not send Host.
    try:
        hostname = urlsplit(f"//{value}").hostname
    except ValueError:
        return False
    return bool(hostname and is_loopback_host(hostname))


def allowed_origin(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return value if is_loopback_host(parsed.hostname) else None
