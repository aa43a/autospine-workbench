"""Request metadata tests for the isolated P10.3c v2 mutation."""

from email.message import Message
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p10_visual_review_v2_http_security import (  # noqa: E402
    INTENT, P10VisualReviewV2HttpSecurityError,
    require_p10_visual_review_v2_headers,
)


def headers(**changes):
    values = {
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:8765",
        "X-Autospine-Intent": INTENT,
        "Sec-Fetch-Site": "same-origin",
    }
    values.update(changes)
    result = Message()
    for name, value in values.items():
        if value is not None:
            result[name] = value
    return result


class P10VisualReviewV2HttpSecurityTests(unittest.TestCase):
    def test_accepts_exact_loopback_origin_and_distinct_intent(self):
        for host in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765"):
            with self.subTest(host=host):
                require_p10_visual_review_v2_headers(headers(
                    Host=host, Origin=f"http://{host}",
                    **{"Sec-Fetch-Site": "none"},
                ))
        self.assertNotEqual("body-sway-visual-review", INTENT)
        self.assertNotEqual("p10-official-runtime-capture-v2", INTENT)

    def test_rejects_missing_cross_port_cross_site_and_old_intents(self):
        cases = (
            headers(Origin=None),
            headers(Origin="http://127.0.0.1:8766"),
            headers(**{"Sec-Fetch-Site": "cross-site"}),
            headers(**{"X-Autospine-Intent": "body-sway-visual-review"}),
            headers(**{"X-Autospine-Intent": "p10-official-runtime-capture-v2"}),
        )
        for value in cases:
            with self.subTest(headers=list(value.items())), self.assertRaises(
                P10VisualReviewV2HttpSecurityError,
            ):
                require_p10_visual_review_v2_headers(value)

    def test_rejects_duplicate_origin(self):
        value = headers()
        value["Origin"] = "http://127.0.0.1:8765"
        with self.assertRaises(P10VisualReviewV2HttpSecurityError):
            require_p10_visual_review_v2_headers(value)


if __name__ == "__main__":
    unittest.main()
