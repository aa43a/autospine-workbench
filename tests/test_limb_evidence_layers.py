"""Public limb evidence loading and semantic boundary tests."""

from __future__ import annotations

import base64
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.candidate_provenance import sha256_file  # noqa: E402
from autospine_workbench.limb_candidates import PoseAlphaLimbProvider  # noqa: E402
from autospine_workbench.limb_evidence_layers import (  # noqa: E402
    is_contact_reference_role,
    is_limb_role,
    joint_role_matches,
    load_limb_evidence,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_limb_candidates import (  # noqa: E402
    observations,
    project_fixture,
)


# Pin the exact evidence bytes used by the provider/document golden. Generating
# this PNG with zlib.compress() made the identity depend on zlib vs zlib-ng.
_FIXED_ARM_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAYAAACNiR0NAAAAIUlEQVR4nGNgGAVUAwFR"
    "Kf+JwaMGjho4auDgNnAUMJALAOg79hlXEaZAAAAAAElFTkSuQmCC"
)


class LimbEvidenceLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.asset = Path(self.directory.name) / "arm.png"
        self.asset.write_bytes(base64.b64decode(_FIXED_ARM_PNG_BASE64, validate=True))
        self.provider = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations()
        )

    def test_loader_exposes_exact_stage_identity_summary(self) -> None:
        evidence = load_limb_evidence(
            project_fixture(),
            self.provider.layer_assets,
            (100, 100),
            self.provider.config,
        )
        self.assertEqual(("layer-arm-left",), tuple(evidence.geometries))
        self.assertEqual("body.hand", evidence.identity_summaries[0]["canonical_role"])
        self.assertEqual(sha256_file(self.asset), evidence.identity_summaries[0]["asset_sha256"])
        self.assertEqual({"NO_LEG_SEMANTIC_LAYER"}, set(evidence.flags))
        self.assertEqual((10, 20), evidence.geometries["layer-arm-left"].offset_xy)
        with self.assertRaises(TypeError):
            evidence.geometries["replacement"] = evidence.geometries["layer-arm-left"]

    def test_role_matching_is_shared_and_explicit(self) -> None:
        self.assertTrue(is_limb_role("body.hand"))
        self.assertTrue(is_limb_role("costume.lower-leg"))
        self.assertFalse(is_limb_role("body.head"))
        self.assertTrue(is_contact_reference_role("body.torso"))
        self.assertFalse(is_contact_reference_role("body.pelvis"))
        self.assertTrue(joint_role_matches("wrist", "body.hand"))
        self.assertTrue(joint_role_matches("hip", "body.pelvis"))
        self.assertFalse(joint_role_matches("knee", "body.pelvis"))

    def test_provider_identity_and_document_match_pre_refactor_golden(self) -> None:
        document = self.provider.analyze(project_fixture())
        self.assertEqual(
            "ac6ec6fabc64041d2c1a93f378b4dc522ca721332d769daa1d2aae1f98627a41",
            document["analysis"]["run_sha256"],
        )
        self.assertEqual(
            "3c9b562a39b3873c260856adebe6b16a55a2a5e8c393af650158fdf16a14b5d0",
            canonical_sha256(document),
        )

    def test_contact_reference_layers_require_explicit_opt_in(self) -> None:
        project = project_fixture()
        torso = {
            "id": "layer-torso",
            "canonical_role": "body.torso",
            "side": "center",
            "disposition": "keep",
            "empty": False,
            "bbox": {"x": 10, "y": 20, "width": 20, "height": 20},
        }
        project["resolved"]["layers"].append(torso)
        assets = {"layer-arm-left": self.asset, "layer-torso": self.asset}

        default = load_limb_evidence(project, assets, (100, 100), self.provider.config)
        expanded = load_limb_evidence(
            project,
            assets,
            (100, 100),
            self.provider.config,
            include_contact_roles=True,
        )

        self.assertNotIn("layer-torso", default.geometries)
        self.assertIn("layer-torso", expanded.geometries)
        self.assertEqual(2, len(expanded.identity_summaries))

    def test_excluded_limb_layer_does_not_require_an_asset(self) -> None:
        project = project_fixture()
        project["resolved"]["layers"][0]["disposition"] = "exclude"
        evidence = load_limb_evidence(
            project,
            {},
            (100, 100),
            self.provider.config,
        )
        self.assertEqual({}, dict(evidence.geometries))
        self.assertEqual((), evidence.identity_summaries)
        self.assertIn("NO_LEG_SEMANTIC_LAYER", evidence.flags)


if __name__ == "__main__":
    unittest.main()
