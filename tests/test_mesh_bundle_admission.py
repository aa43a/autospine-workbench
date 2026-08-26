"""Tests for the shared exact P3 mesh-bundle admission boundary."""

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

from autospine_workbench.mesh_bundle_admission import (  # noqa: E402
    MeshBundleAdmissionError,
    require_exact_mesh_bundle,
)
from tests.depth_order_helpers import DepthOrderFixture  # noqa: E402


class MeshBundleAdmissionTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return DepthOrderFixture(Path(temporary.name)).mesh

    def test_returns_an_isolated_rig_after_exact_rebuild(self):
        bundle = self.fixture()
        first = require_exact_mesh_bundle(bundle)
        first["slots"][0]["id"] = "changed"
        self.assertNotEqual(first, require_exact_mesh_bundle(bundle))

    def test_identity_and_type_spoofing_fail_closed(self):
        bundle = self.fixture()
        with self.assertRaises(MeshBundleAdmissionError):
            require_exact_mesh_bundle(replace(bundle, rig_sha256="f" * 64))
        with self.assertRaises(MeshBundleAdmissionError):
            require_exact_mesh_bundle(object())


if __name__ == "__main__":
    unittest.main()
