"""Tests for local HTTP access-log redaction."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.http_log_redaction import (  # noqa: E402
    redact_http_log_arguments,
)


class HttpLogRedactionTests(unittest.TestCase):
    def test_image_session_is_redacted_without_changing_other_values(self):
        values = (
            "GET /frame.png?session=secret-token HTTP/1.1",
            200, "123",
        )
        self.assertEqual((
            "GET /frame.png?session=<redacted> HTTP/1.1",
            200, "123",
        ), redact_http_log_arguments(values))

    def test_non_session_request_is_unchanged(self):
        values = ("GET /api/projects HTTP/1.1", 200, "42")
        self.assertEqual(values, redact_http_log_arguments(values))

    def test_percent_encoded_session_key_is_also_redacted(self):
        token = "s" * 43
        values = (f"GET /frame.png?sess%69on={token} HTTP/1.1",)
        self.assertEqual((
            "GET /frame.png?sess%69on=<redacted> HTTP/1.1",
        ), redact_http_log_arguments(values))


if __name__ == "__main__":
    unittest.main()
