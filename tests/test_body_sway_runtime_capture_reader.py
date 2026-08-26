"""Strict exact-address P10 runtime capture reader tests."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_runtime_capture_reader import (  # noqa: E402
    VerifiedBodySwayRuntimeCaptureNotFound,
    VerifiedBodySwayRuntimeCaptureReader,
    VerifiedBodySwayRuntimeCaptureReaderError,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.body_sway_visual_review_helpers import (  # noqa: E402
    BodySwayVisualReviewFixture,
)


class VerifiedBodySwayRuntimeCaptureReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = BodySwayVisualReviewFixture(self.root)
        self.reader = VerifiedBodySwayRuntimeCaptureReader(
            self.fixture.state_root
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load(self):
        with fake_runtime_profile():
            return self.reader.load(*self.fixture.address)

    def test_loads_only_the_full_explicit_address_without_writing(self) -> None:
        before = sorted(path.relative_to(self.fixture.state_root)
                        for path in self.fixture.state_root.rglob("*"))
        verified = self.load()
        after = sorted(path.relative_to(self.fixture.state_root)
                       for path in self.fixture.state_root.rglob("*"))

        self.assertEqual(before, after)
        self.assertEqual(self.fixture.published.path, verified.path)
        self.assertEqual(self.fixture.capture.canonical_bytes,
                         verified.capture.canonical_bytes)
        self.assertEqual(self.fixture.capture.capture_bytes,
                         verified.capture.capture_bytes)
        self.assertEqual(self.fixture.published.bundle_sha256,
                         verified.bundle_sha256)
        self.assertFalse((verified.path.parent / "latest").exists())

    def test_every_address_component_and_artifact_seal_is_required(self) -> None:
        values = list(self.fixture.address)
        replacements = ("wrong-project", "a" * 64, "c" * 64, "d" * 64)
        for index, replacement in enumerate(replacements):
            with self.subTest(index=index):
                changed = list(values)
                changed[index] = replacement
                with fake_runtime_profile(), self.assertRaises(
                    VerifiedBodySwayRuntimeCaptureReaderError
                ):
                    self.reader.load(*changed)

        with self.assertRaises(VerifiedBodySwayRuntimeCaptureReaderError):
            self.reader.load(values[0], values[1], "latest", values[3])

    def test_missing_address_does_not_create_state(self) -> None:
        absent = self.root / "absent"
        reader = VerifiedBodySwayRuntimeCaptureReader(absent)
        with self.assertRaises(VerifiedBodySwayRuntimeCaptureNotFound):
            reader.load(*self.fixture.address)
        self.assertFalse(absent.exists())

    def test_missing_path_is_typed_but_artifact_mismatch_is_not(self) -> None:
        address = list(self.fixture.address)
        missing_bundle = [*address[:2], "a" * 64, address[3]]
        with fake_runtime_profile(), self.assertRaises(
            VerifiedBodySwayRuntimeCaptureNotFound
        ):
            self.reader.load(*missing_bundle)

        wrong_artifact = [*address[:3], "a" * 64]
        with fake_runtime_profile(), self.assertRaises(
            VerifiedBodySwayRuntimeCaptureReaderError
        ) as raised:
            self.reader.load(*wrong_artifact)
        self.assertNotIsInstance(
            raised.exception, VerifiedBodySwayRuntimeCaptureNotFound
        )

    def test_changed_bytes_extra_inventory_and_wrong_case_fail_closed(self) -> None:
        def changed_png(path):
            image = next((path / "captures").iterdir())
            payload = image.read_bytes()
            image.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))

        mutations = (
            lambda path: (path / "body-sway-runtime-capture.json").write_bytes(
                (path / "body-sway-runtime-capture.json").read_bytes() + b" "
            ),
            lambda path: (path / "captures" / "foreign.png").write_bytes(b"x"),
            lambda path: (path / "foreign.txt").write_bytes(b"x"),
            changed_png,
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                fixture = BodySwayVisualReviewFixture(self.root / f"case-{index}")
                mutation(fixture.published.path)
                with fake_runtime_profile(), self.assertRaises(
                    VerifiedBodySwayRuntimeCaptureReaderError
                ):
                    VerifiedBodySwayRuntimeCaptureReader(
                        fixture.state_root
                    ).load(*fixture.address)

        fixture = BodySwayVisualReviewFixture(self.root / "wrong-case")
        manifest = fixture.published.path / "body-sway-runtime-capture.json"
        renamed = fixture.published.path / "BODY-SWAY-RUNTIME-CAPTURE.JSON"
        manifest.rename(renamed)
        with fake_runtime_profile(), self.assertRaises(
            VerifiedBodySwayRuntimeCaptureReaderError
        ):
            VerifiedBodySwayRuntimeCaptureReader(
                fixture.state_root
            ).load(*fixture.address)

    def test_aliased_state_root_is_never_evidence(self) -> None:
        alias = self.root / "alias-state"
        try:
            alias.symlink_to(self.fixture.state_root, target_is_directory=True)
        except OSError:
            return
        try:
            with fake_runtime_profile(), self.assertRaises(
                VerifiedBodySwayRuntimeCaptureReaderError
            ):
                VerifiedBodySwayRuntimeCaptureReader(alias).load(
                    *self.fixture.address
                )
        finally:
            alias.unlink()


if __name__ == "__main__":
    unittest.main()
