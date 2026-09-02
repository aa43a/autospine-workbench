"""Tests for bounded non-authoritative P10.3c image read sessions."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_visual_review_address_v2 import (  # noqa: E402
    ExactVisualReviewAddressV2,
)
from autospine_workbench.body_sway_visual_review_application_models_v2 import (  # noqa: E402
    BodySwayVisualReviewImageV2,
)
from autospine_workbench.p10_visual_review_v2_image_cache import (  # noqa: E402
    P10VisualReviewV2ImageCacheNotFound,
    P10VisualReviewV2ImageCacheKey,
    P10VisualReviewV2ImageReplayCache,
)
from autospine_workbench.p10_visual_review_v2_image_session import (  # noqa: E402
    P10VisualReviewV2ImageSessionError,
    P10VisualReviewV2ImageSessionNotFound,
    P10VisualReviewV2ImageSessionStore,
)


SHA = lambda value: value * 64


class P10VisualReviewV2ImageSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.now = [10.0]
        self.tokens = iter(("s" * 43, "t" * 43, "u" * 43))
        self.store = P10VisualReviewV2ImageSessionStore(
            self.root, capacity=2, ttl_seconds=120,
            clock=lambda: self.now[0], token_factory=lambda: next(self.tokens),
        )
        self.key = _key("a", "b", "f")
        self.raw = b"PNG-SESSION"
        self.png = hashlib.sha256(self.raw).hexdigest()
        self.image = BodySwayVisualReviewImageV2(
            SHA("f"), "case-1", SHA("9"), self.png,
            len(self.raw), 640, 640, self.raw,
        )
        self.loads = 0

    def tearDown(self):
        self.temporary.cleanup()

    def loader(self):
        self.loads += 1
        return (self.image,)

    def test_open_verifies_snapshot_and_reuses_exact_bytes(self):
        session = self.store.open(self.key, loader=self.loader)
        self.assertEqual(1, self.loads)
        self.assertEqual({
            "format_version": 1, "token": "s" * 43,
            "expires_in_seconds": 120,
            "authority": "read_only_snapshot",
        }, session.public_document())
        for _ in range(2):
            loaded = self.store.image(
                session.token, job_id=SHA("a"),
                candidate_sha256=SHA("f"), case_id="case-1",
                png_sha256=self.png,
            )
            self.assertEqual(self.raw, loaded.png_bytes)
        self.assertEqual(1, self.loads)

    def test_cache_eviction_reuses_bound_bytes_without_replaying_loader(self):
        cache = P10VisualReviewV2ImageReplayCache(self.root, capacity=1)
        tokens = iter(("v" * 43, "w" * 43))
        store = P10VisualReviewV2ImageSessionStore(
            self.root, image_cache=cache, capacity=2,
            token_factory=lambda: next(tokens),
        )
        first = store.open(self.key, loader=self.loader)
        other = BodySwayVisualReviewImageV2(
            SHA("e"), "case-1", SHA("8"), self.png,
            len(self.raw), 640, 640, self.raw,
        )
        store.open(_key("b", "c", "e"), loader=lambda: (other,))

        loaded = store.image(
            first.token, job_id=SHA("a"), candidate_sha256=SHA("f"),
            case_id="case-1", png_sha256=self.png,
        )
        self.assertEqual(self.raw, loaded.png_bytes)
        self.assertEqual(1, self.loads)

    def test_expiration_is_absolute_and_does_not_fallback(self):
        session = self.store.open(self.key, loader=self.loader)
        self.now[0] = 129.9
        self.assertIsNotNone(self.store.image(
            session.token, job_id=SHA("a"),
            candidate_sha256=SHA("f"), case_id="case-1",
            png_sha256=self.png,
        ))
        self.now[0] = 130.0
        self.assertIsNone(self.store.image(
            session.token, job_id=SHA("a"),
            candidate_sha256=SHA("f"), case_id="case-1",
            png_sha256=self.png,
        ))

    def test_crosswired_identity_is_rejected(self):
        session = self.store.open(self.key, loader=self.loader)
        with self.assertRaises(P10VisualReviewV2ImageSessionNotFound):
            self.store.image(
                session.token, job_id=SHA("0"),
                candidate_sha256=SHA("f"), case_id="case-1",
                png_sha256=self.png,
            )
        with self.assertRaises(P10VisualReviewV2ImageCacheNotFound):
            self.store.image(
                session.token, job_id=SHA("a"),
                candidate_sha256=SHA("f"), case_id="other",
                png_sha256=self.png,
            )

    def test_capacity_evicts_oldest_session(self):
        first = self.store.open(self.key, loader=self.loader)
        second = self.store.open(_key("b", "c", "f"), loader=self.loader)
        third = self.store.open(_key("c", "d", "f"), loader=self.loader)
        self.assertIsNone(self.store.image(
            first.token, job_id=SHA("a"), candidate_sha256=SHA("f"),
            case_id="case-1", png_sha256=self.png,
        ))
        self.assertEqual(("t" * 43, "u" * 43), (second.token, third.token))

    def test_byte_capacity_evicts_oldest_bound_snapshot(self):
        tokens = iter(("x" * 43, "y" * 43))
        store = P10VisualReviewV2ImageSessionStore(
            self.root, capacity=2, byte_capacity=len(self.raw),
            token_factory=lambda: next(tokens),
        )
        first = store.open(self.key, loader=self.loader)
        second = store.open(_key("b", "c", "f"), loader=self.loader)
        self.assertIsNone(store.image(
            first.token, job_id=SHA("a"), candidate_sha256=SHA("f"),
            case_id="case-1", png_sha256=self.png,
        ))
        self.assertIsNotNone(store.image(
            second.token, job_id=SHA("b"), candidate_sha256=SHA("f"),
            case_id="case-1", png_sha256=self.png,
        ))

    def test_failed_snapshot_does_not_issue_session(self):
        with self.assertRaises(RuntimeError):
            self.store.open(
                self.key,
                loader=lambda: (_ for _ in ()).throw(RuntimeError("private")),
            )
        session = self.store.open(self.key, loader=self.loader)
        self.assertEqual("s" * 43, session.token)

    def test_invalid_dependencies_fail_closed(self):
        for kwargs in (
            {"capacity": 0}, {"byte_capacity": 0},
            {"ttl_seconds": 0}, {"clock": None},
            {"token_factory": lambda: "unsafe token"},
        ):
            with self.subTest(kwargs=tuple(kwargs)):
                if "token_factory" in kwargs:
                    store = P10VisualReviewV2ImageSessionStore(
                        self.root, **kwargs,
                    )
                    with self.assertRaises(P10VisualReviewV2ImageSessionError):
                        store.open(self.key, loader=self.loader)
                else:
                    with self.assertRaises(P10VisualReviewV2ImageSessionError):
                        P10VisualReviewV2ImageSessionStore(self.root, **kwargs)


def _key(job, package, candidate):
    return P10VisualReviewV2ImageCacheKey(
        SHA(job), SHA(package),
        ExactVisualReviewAddressV2(
            "fixture-project", SHA("1"), SHA("2"), SHA("3"),
        ),
        SHA(candidate),
    )


if __name__ == "__main__":
    unittest.main()
