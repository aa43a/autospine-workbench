"""Bounded BVH byte-tokenizer tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_tokens import (  # noqa: E402
    BvhTokenError,
    tokenize_bvh,
)


class BvhTokenizerTests(unittest.TestCase):
    def test_raw_sha_locations_braces_and_crlf_are_deterministic(self) -> None:
        raw = b"A {\r\nB}"
        first = tokenize_bvh(raw)
        second = tokenize_bvh(raw)

        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), first.source_sha256)
        self.assertEqual(len(raw), first.source_byte_length)
        self.assertEqual(
            [
                ("A", 0, 1, 1), ("{", 2, 1, 3),
                ("B", 5, 2, 1), ("}", 6, 2, 2),
            ],
            [
                (item.text, item.byte_offset, item.line, item.column)
                for item in first.tokens
            ],
        )
        self.assertEqual((2, 3), (first.end_line, first.end_column))

    def test_non_ascii_and_control_errors_include_precise_location(self) -> None:
        for raw in (b"A\r\nB\xff", b"A\r\nB\x00"):
            with self.subTest(raw=raw), self.assertRaisesRegex(
                BvhTokenError, r"byte 4 \(line 2, column 2\)"
            ):
                tokenize_bvh(raw)

    def test_source_token_and_token_count_budgets_fail_closed(self) -> None:
        cases = (
            ("MAX_BVH_BYTES", 2, b"ABC", "source exceeds"),
            ("MAX_BVH_TOKEN_BYTES", 2, b"ABC", "token exceeds"),
            ("MAX_BVH_TOKENS", 1, b"A B", "token count exceeds"),
        )
        for constant, limit, raw, message in cases:
            with (
                self.subTest(constant=constant),
                patch(f"autospine_workbench.bvh_tokens.{constant}", limit),
                self.assertRaisesRegex(BvhTokenError, message),
            ):
                tokenize_bvh(raw)

    def test_exact_byte_token_and_token_count_boundaries_are_admitted(self) -> None:
        raw = b"ABC DEF"
        with (
            patch("autospine_workbench.bvh_tokens.MAX_BVH_BYTES", len(raw)),
            patch("autospine_workbench.bvh_tokens.MAX_BVH_TOKEN_BYTES", 3),
            patch("autospine_workbench.bvh_tokens.MAX_BVH_TOKENS", 2),
        ):
            stream = tokenize_bvh(raw)
        self.assertEqual(("ABC", "DEF"), tuple(t.text for t in stream.tokens))

    def test_only_an_immutable_bytes_snapshot_is_accepted(self) -> None:
        with self.assertRaisesRegex(BvhTokenError, "immutable bytes"):
            tokenize_bvh(bytearray(b"HIERARCHY"))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
