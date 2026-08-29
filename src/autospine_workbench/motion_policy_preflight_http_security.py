"""Same-origin metadata guard for zero-write motion-policy preflight."""

from __future__ import annotations

from urllib.parse import urlsplit

from .http_security import is_loopback_host


INTENT_HEADER = "X-Autospine-Intent"
INTENT_VALUE = "motion-policy-preflight-v1"


class MotionPolicyPreflightHttpSecurityError(ValueError):
    """Public-safe rejection of preflight request metadata."""

    def __init__(self, code: str, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def require_motion_policy_preflight_headers(headers) -> None:
    """Require one explicit loopback Host/Origin pair and intent token."""

    host = _one(headers, "Host", required=True, code="forbidden_host")
    if not _loopback_authority(host):
        raise MotionPolicyPreflightHttpSecurityError(
            "forbidden_host", "Host must be an explicit loopback authority."
        )
    origin = _one(headers, "Origin", required=True, code="forbidden_origin")
    if origin != f"http://{host}":
        raise MotionPolicyPreflightHttpSecurityError(
            "forbidden_origin", "Origin must exactly match the local Host."
        )
    intent = _one(headers, INTENT_HEADER, required=True,
                  code="forbidden_intent")
    if intent != INTENT_VALUE:
        raise MotionPolicyPreflightHttpSecurityError(
            "forbidden_intent", "Motion-policy preflight intent is missing."
        )
    fetch_site = _one(
        headers, "Sec-Fetch-Site", required=False,
        code="forbidden_fetch_site",
    )
    if fetch_site is not None and fetch_site not in {"same-origin", "none"}:
        raise MotionPolicyPreflightHttpSecurityError(
            "forbidden_fetch_site",
            "Motion-policy preflight request is not same-origin.",
        )


def _one(headers, name: str, *, required: bool, code: str) -> str | None:
    try:
        values = headers.get_all(name, []) or []
    except (AttributeError, TypeError, ValueError) as exc:
        raise MotionPolicyPreflightHttpSecurityError(
            code, f"{name} header is invalid."
        ) from exc
    if len(values) != 1:
        if not values and not required:
            return None
        raise MotionPolicyPreflightHttpSecurityError(
            code, f"Exactly one {name} header is required."
        )
    value = values[0]
    if type(value) is not str or not value or value != value.strip() \
            or any(character in value for character in "\r\n\0"):
        raise MotionPolicyPreflightHttpSecurityError(
            code, f"{name} header is invalid."
        )
    return value


def _loopback_authority(value: str) -> bool:
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port
    except (TypeError, ValueError):
        return False
    return bool(
        parsed.hostname and is_loopback_host(parsed.hostname)
        and parsed.username is None and parsed.password is None
        and not parsed.path and not parsed.query and not parsed.fragment
        and (port is None or 0 <= port <= 65535)
    )
