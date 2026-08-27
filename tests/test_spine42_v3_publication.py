"""Integrated immutable publication and historical replay for P10.7a."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_bundle_files import NAMESPACE  # noqa: E402
from autospine_workbench.spine42_v3_bundle_reader import (  # noqa: E402
    VerifiedSpine42V3BundleReader,
)
from autospine_workbench.spine42_v3_bundle_store import (  # noqa: E402
    Spine42V3BundleStore,
)
from autospine_workbench.spine42_v3_pipeline import (  # noqa: E402
    VerifiedSpine42V3Pipeline,
)
from tests.spine42_v3_storage_helpers import (  # noqa: E402
    Spine42V3StorageFixture,
)


class Spine42V3PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = Spine42V3StorageFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def publish(self):
        source = self.fixture.published_v3
        with self.fixture.compile_gate():
            return Spine42V3BundleStore(self.fixture.state_root).publish(
                self.fixture.project_id,
                source.motion_instance_v3_sha256,
                source.bundle_sha256,
            )

    def read(self, published):
        with self.fixture.replay_gate():
            return VerifiedSpine42V3BundleReader(
                self.fixture.state_root
            ).load(
                self.fixture.project_id,
                published.skeleton_json_sha256,
                published.bundle_sha256,
            )

    def test_pipeline_store_reader_and_reuse_are_exact(self):
        source = self.fixture.published_v3
        with self.fixture.replay_gate():
            compiled = VerifiedSpine42V3Pipeline(
                self.fixture.state_root
            ).build(
                self.fixture.project_id,
                source.motion_instance_v3_sha256,
                source.bundle_sha256,
            )
        first = self.publish()
        verified = self.read(first)
        second = self.publish()
        self.assertIs(type(first.reused), bool)
        self.assertTrue(second.reused)
        self.assertEqual(compiled.contract_identities,
                         verified.contract_identities)
        self.assertEqual(compiled.document_bytes, verified.document_bytes)
        self.assertEqual(
            (first.path.name, first.path.parent.name,
             first.path.parent.parent.name),
            (compiled.bundle_sha256, compiled.skeleton_json_sha256, NAMESPACE),
        )

    def test_run_grants_only_adapter_emission(self):
        run = self.read(self.publish()).run_manifest
        self.assertEqual({
            "spine_adapter_emitted": True,
            "official_runtime_loaded": False,
            "raster_visual_quality": False,
            "persistent_current_head_authority": False,
            "publishable_spine_timeline": False,
            "release_authority": False,
        }, run["authority"])
        self.assertEqual("blocked", run["release_gate"]["status"])
        self.assertNotIn(str(self.fixture.root), json.dumps(run))

    def test_historical_reader_never_observes_current_heads(self):
        published = self.publish()
        with self.fixture.replay_gate(), patch(
            "autospine_workbench.spine42_v3_current_heads."
            "require_current_body_sway_dynamic_seam_heads",
            side_effect=AssertionError("historical head check attempted"),
        ) as current:
            verified = VerifiedSpine42V3BundleReader(
                self.fixture.state_root
            ).load(
                self.fixture.project_id,
                published.skeleton_json_sha256,
                published.bundle_sha256,
            )
        current.assert_not_called()
        self.assertEqual(published.bundle_sha256, verified.bundle_sha256)


if __name__ == "__main__":
    unittest.main()
