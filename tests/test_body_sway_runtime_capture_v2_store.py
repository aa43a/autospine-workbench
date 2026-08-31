"""Immutable RuntimeCapture v2 store and exact-reader tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_runtime_capture_v2_profile import (  # noqa: E402
    MANIFEST_NAME,
    NAMESPACE,
)
from autospine_workbench.body_sway_runtime_capture_v2_reader import (  # noqa: E402
    VerifiedBodySwayRuntimeCaptureV2NotFound,
    VerifiedBodySwayRuntimeCaptureV2Reader,
    VerifiedBodySwayRuntimeCaptureV2ReaderError,
)
from autospine_workbench.body_sway_runtime_capture_v2_store import (  # noqa: E402
    BodySwayRuntimeCaptureV2Store,
    BodySwayRuntimeCaptureV2StoreError,
)
from tests.body_sway_runtime_capture_v2_helpers import (  # noqa: E402
    RuntimeCaptureV2Fixture,
)


class BodySwayRuntimeCaptureV2StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = RuntimeCaptureV2Fixture(self.root / "inputs")
        self.state = self.root / "state"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish(self):
        return BodySwayRuntimeCaptureV2Store(self.state).publish(
            self.fixture.capture
        )

    def test_publish_is_content_addressed_and_exact_reuse(self) -> None:
        first, second = self.publish(), self.publish()
        expected = (
            self.state / "builds" / self.fixture.capture.document["project_id"]
            / NAMESPACE
            / self.fixture.capture.document["source"][
                "temporary_preview_v2_sha256"
            ] / first.bundle_sha256
        )
        self.assertEqual(expected, first.path)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual({MANIFEST_NAME, "captures"},
                         {item.name for item in expected.iterdir()})
        self.assertFalse((expected.parent / "latest").exists())

    def test_exact_reader_round_trips_without_writing(self) -> None:
        published = self.publish()
        before = sorted(path.relative_to(self.state)
                        for path in self.state.rglob("*"))
        loaded = VerifiedBodySwayRuntimeCaptureV2Reader(self.state).load(
            published.project_id,
            published.temporary_preview_v2_sha256,
            published.bundle_sha256,
            published.artifact_set_sha256,
        )
        after = sorted(path.relative_to(self.state)
                       for path in self.state.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(self.fixture.capture.canonical_bytes,
                         loaded.capture.canonical_bytes)
        self.assertEqual(self.fixture.capture.capture_bytes,
                         loaded.capture.capture_bytes)

    def test_reader_requires_all_four_exact_address_components(self) -> None:
        published = self.publish()
        address = [
            published.project_id, published.temporary_preview_v2_sha256,
            published.bundle_sha256, published.artifact_set_sha256,
        ]
        replacements = ("wrong-project", "a" * 64, "b" * 64, "c" * 64)
        for index, replacement in enumerate(replacements):
            with self.subTest(index=index):
                changed = list(address)
                changed[index] = replacement
                with self.assertRaises(VerifiedBodySwayRuntimeCaptureV2ReaderError):
                    VerifiedBodySwayRuntimeCaptureV2Reader(self.state).load(
                        *changed
                    )
        with self.assertRaises(VerifiedBodySwayRuntimeCaptureV2ReaderError):
            VerifiedBodySwayRuntimeCaptureV2Reader(self.state).load(
                address[0], "latest", address[2], address[3]
            )

    def test_missing_store_is_typed_and_does_not_create_state(self) -> None:
        absent = self.root / "absent"
        source = self.fixture.capture.document["source"]
        with self.assertRaises(VerifiedBodySwayRuntimeCaptureV2NotFound):
            VerifiedBodySwayRuntimeCaptureV2Reader(absent).load(
                self.fixture.capture.document["project_id"],
                source["temporary_preview_v2_sha256"],
                "a" * 64, self.fixture.capture.artifact_set_sha256,
            )
        self.assertFalse(absent.exists())

    def test_concurrent_publications_converge(self) -> None:
        store = BodySwayRuntimeCaptureV2Store(self.state)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _index: store.publish(self.fixture.capture), range(12)
            ))
        self.assertEqual(1, len({result.path for result in results}))
        self.assertEqual(1, sum(not result.reused for result in results))

    def test_existing_tamper_is_never_overwritten(self) -> None:
        published = self.publish()
        manifest = published.path / MANIFEST_NAME
        manifest.write_bytes(manifest.read_bytes() + b" ")
        with self.assertRaises(BodySwayRuntimeCaptureV2StoreError):
            self.publish()
        self.assertTrue(manifest.read_bytes().endswith(b" "))

    def test_extra_and_changed_png_fail_closed(self) -> None:
        published = self.publish()
        (published.path / "captures" / "foreign.png").write_bytes(b"x")
        with self.assertRaises((
            BodySwayRuntimeCaptureV2StoreError,
            VerifiedBodySwayRuntimeCaptureV2ReaderError,
        )):
            VerifiedBodySwayRuntimeCaptureV2Reader(self.state).load(
                published.project_id,
                published.temporary_preview_v2_sha256,
                published.bundle_sha256,
                published.artifact_set_sha256,
            )


if __name__ == "__main__":
    unittest.main()
