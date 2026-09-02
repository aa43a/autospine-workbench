"""Literal hashes that keep the frozen P10.6/P10.7 v1 path isolated."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_bundle_store import (  # noqa: E402
    Spine42V3BundleStore,
)
from tests.spine42_v3_storage_helpers import (  # noqa: E402
    Spine42V3StorageFixture,
)


class P106FrozenV1RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = Spine42V3StorageFixture(Path(cls.temporary.name))
        source = cls.fixture.published_v3
        with cls.fixture.compile_gate():
            cls.spine = Spine42V3BundleStore(
                cls.fixture.state_root
            ).publish(
                cls.fixture.project_id,
                source.motion_instance_v3_sha256,
                source.bundle_sha256,
            )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_p106a_and_motion_instance_v3_hashes_remain_literal(self):
        self.assertEqual(
            "e17f0c38af77e76db91e4cd0e75068c7b770875d8b4269a95bd268e8f56b600e",
            self.fixture.admission.sha256,
        )
        self.assertEqual(
            "329e273a5833e7782f1160e3c5f64b1a68bc0b227f358babaf35442d56be655d",
            self.fixture.motion_instance_v3.sha256,
        )
        self.assertEqual(
            "28cbce08bae7df6a98341e955a1d6ab60adfb53cdad5e1b5728d4298e2787b30",
            self.fixture.published_v3.bundle_sha256,
        )

    def test_p107a_spine_adapter_hashes_remain_literal(self):
        self.assertEqual(
            "b0e91e69741b0f95f834873b376518ae6820a6c4b8dfd92eb66cb66de9932add",
            self.spine.skeleton_json_sha256,
        )
        self.assertEqual(
            "206bce0ae736fd085d6cbbe400233fef46cf86d5075034a99904539f66bc6422",
            self.spine.bundle_sha256,
        )


if __name__ == "__main__":
    unittest.main()
