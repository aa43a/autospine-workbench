"""Publication and exact replay tests for ProjectedMotionIR bundles."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.immutable_bundle_fs import (  # noqa: E402
    ImmutableBundleSnapshot,
    framed_bundle_sha256,
)
from autospine_workbench.projected_motion_bundle_contract import (  # noqa: E402
    BUNDLE_ADDRESS_DOMAIN,
    DOCUMENT_NAMES,
)
from autospine_workbench.projected_motion_bundle_integrity import (  # noqa: E402
    ProjectedMotionBundleIntegrityError,
    verify_projected_motion_bundle_snapshot,
)
from autospine_workbench.projected_motion_bundle_reader import (  # noqa: E402
    VerifiedProjectedMotionBundleReader,
    VerifiedProjectedMotionBundleReaderError,
)
from tests.projected_motion_bundle_helpers import (  # noqa: E402
    ProjectedBundleFixture,
)


class ProjectedMotionBundleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = ProjectedBundleFixture(self.root)

    def test_publish_reuse_and_read_only_exact_replay(self):
        first, second = self.fixture.publish(), self.fixture.publish()
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual(set(DOCUMENT_NAMES), {
            path.name for path in first.path.iterdir()
        })
        self.assertFalse((first.path / "source.npz").exists())
        before = sorted(
            path.relative_to(self.fixture.state)
            for path in self.fixture.state.rglob("*")
        )
        verified = VerifiedProjectedMotionBundleReader(
            self.fixture.state
        ).load(first.projected_motion_sha256, first.bundle_sha256)
        after = sorted(
            path.relative_to(self.fixture.state)
            for path in self.fixture.state.rglob("*")
        )
        self.assertEqual(before, after)
        self.assertEqual(first.bundle_sha256, verified.bundle_sha256)
        self.assertEqual(self.fixture.p7.bundle_sha256,
                         verified.p7_bundle_sha256)
        self.assertEqual(self.fixture.p7.motion, verified.legacy_motion)
        self.assertEqual(DOCUMENT_NAMES, verified.inventory)

    def test_reader_recompiles_projected_geometry_exactly_once(self):
        published = self.fixture.publish()
        from autospine_workbench import projected_motion_bundle_integrity as integrity
        with patch.object(
            integrity,
            "compile_verified_kimodo_projection",
            wraps=integrity.compile_verified_kimodo_projection,
        ) as call:
            VerifiedProjectedMotionBundleReader(self.fixture.state).load(
                published.projected_motion_sha256,
                published.bundle_sha256,
            )
        self.assertEqual(1, call.call_count)

    def test_each_tampered_document_fails_exact_readback(self):
        for name in DOCUMENT_NAMES:
            with self.subTest(name=name):
                fixture = ProjectedBundleFixture(
                    self.root / name.replace(".", "-")
                )
                published = fixture.publish()
                path = published.path / name
                path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises(VerifiedProjectedMotionBundleReaderError):
                    VerifiedProjectedMotionBundleReader(fixture.state).load(
                        published.projected_motion_sha256,
                        published.bundle_sha256,
                    )

    def test_inventory_case_and_exact_address_fail_closed(self):
        published = self.fixture.publish()
        (published.path / "extra.json").write_bytes(b"{}")
        reader = VerifiedProjectedMotionBundleReader(self.fixture.state)
        with self.assertRaises(VerifiedProjectedMotionBundleReaderError):
            reader.load(
                published.projected_motion_sha256, published.bundle_sha256
            )
        with self.assertRaises(VerifiedProjectedMotionBundleReaderError):
            reader.load("A" * 64, published.bundle_sha256)

    def test_upstream_p7_tamper_breaks_projected_replay(self):
        published = self.fixture.publish()
        p7_npz = self.fixture.p7.path / "source.npz"
        p7_npz.write_bytes(p7_npz.read_bytes() + b"x")
        with self.assertRaisesRegex(
            VerifiedProjectedMotionBundleReaderError, "load failed"
        ):
            VerifiedProjectedMotionBundleReader(self.fixture.state).load(
                published.projected_motion_sha256, published.bundle_sha256
            )

    def test_duplicate_json_key_fails_before_upstream_replay(self):
        published = self.fixture.publish()
        payloads = tuple(
            (published.path / name).read_bytes() for name in DOCUMENT_NAMES
        )
        camera = b'{"format":"duplicate",' + payloads[0][1:]
        changed = (camera, payloads[1], payloads[2])
        address = framed_bundle_sha256(
            BUNDLE_ADDRESS_DOMAIN,
            DOCUMENT_NAMES,
            dict(zip(DOCUMENT_NAMES, changed)),
        )
        snapshot = ImmutableBundleSnapshot(
            path=self.fixture.state / "projected-motions"
                / published.projected_motion_sha256 / address,
            primary_sha256=published.projected_motion_sha256,
            bundle_sha256=address,
            ordered_names=DOCUMENT_NAMES,
            payloads=changed,
        )
        with self.assertRaisesRegex(
            ProjectedMotionBundleIntegrityError, "duplicate"
        ):
            verify_projected_motion_bundle_snapshot(
                snapshot, state_root=self.fixture.state
            )


if __name__ == "__main__":
    unittest.main()
