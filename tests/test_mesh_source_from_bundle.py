"""Zero-I/O P3 bundle-to-source-image adapter tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_source_from_bundle import (  # noqa: E402
    VerifiedMeshBundleSourceError,
    verified_mesh_source_from_bundle,
)
from tests.p10_candidate_helpers import P10PersistedFixture  # noqa: E402


class VerifiedMeshSourceFromBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10PersistedFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_reuses_verified_snapshot_with_complete_exact_images(self):
        bundle = self.fixture.mesh
        source = verified_mesh_source_from_bundle(bundle)
        self.assertEqual(
            (bundle.project_id, bundle.rig_sha256, bundle.bundle_sha256),
            source.p3_address,
        )
        self.assertEqual(bundle.rig, source.rig)
        expected = {
            row["id"]: row["image_sha256"]
            for row in bundle.rig["attachments"]
        }
        self.assertEqual(
            expected,
            {row.attachment_id: row.image_sha256 for row in source.images},
        )
        self.assertEqual(4, len(source.png_by_attachment))

    def test_stale_rig_or_tampered_source_png_fails_closed(self):
        with self.assertRaisesRegex(
            VerifiedMeshBundleSourceError, "RigIR identity"
        ):
            verified_mesh_source_from_bundle(replace(
                self.fixture.mesh, rig_sha256="f" * 64
            ))
        path, raw = self.fixture.mesh._source_png_items[0]
        damaged = replace(
            self.fixture.mesh,
            _source_png_items=((path, raw + b"x"),)
            + self.fixture.mesh._source_png_items[1:],
        )
        with self.assertRaises(VerifiedMeshBundleSourceError):
            verified_mesh_source_from_bundle(damaged)

    def test_requires_the_exact_verified_bundle_type(self):
        with self.assertRaisesRegex(
            VerifiedMeshBundleSourceError, "exact verified"
        ):
            verified_mesh_source_from_bundle(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
