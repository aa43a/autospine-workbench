"""Cross-document geometry reference validation tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.geometry_candidate_binding import (  # noqa: E402
    require_geometry_candidate_binding,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402


def geometry_document() -> dict:
    return {
        "layers": [
            {
                "layer_id": "arm-left",
                "components": [{"component_id": 0}, {"component_id": 2}],
            }
        ],
        "paths": [{"path_id": "arm.left"}],
        "contacts": [{"contact_id": "shoulder.left"}],
    }


def candidate_document(evidence: list[dict]) -> dict:
    return {
        "joints": {
            "elbow.left": {
                "candidates": [{"evidence": evidence}],
            }
        }
    }


class GeometryCandidateBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.geometry = geometry_document()
        self.digest = canonical_sha256(self.geometry)
        self.prefix = f"alpha-geometry-evidence:{self.digest}#"

    def test_accepts_existing_fragments_compatible_with_evidence_kind(self) -> None:
        candidates = candidate_document([
            {"kind": "layer_alpha", "source_ref": self.prefix + "layers/arm-left"},
            {
                "kind": "layer_alpha",
                "source_ref": self.prefix + "layers/arm-left/components/2",
            },
            {"kind": "layer_alpha", "source_ref": self.prefix + "paths/arm.left"},
            {
                "kind": "kinematic_residual",
                "source_ref": self.prefix + "paths/arm.left",
            },
            {
                "kind": "contact_geometry",
                "source_ref": self.prefix + "contacts/shoulder.left",
            },
            {"kind": "pose_heatmap", "source_ref": "pose-observations:pinned"},
        ])

        self.assertEqual(
            self.digest,
            require_geometry_candidate_binding(candidates, self.geometry),
        )

    def test_rejects_stale_or_nonexistent_geometry_targets(self) -> None:
        cases = {
            "missing ref": {"kind": "layer_alpha"},
            "wrong sha": {
                "kind": "layer_alpha",
                "source_ref": f"alpha-geometry-evidence:{'f' * 64}#layers/arm-left",
            },
            "wrong path": {
                "kind": "kinematic_residual",
                "source_ref": self.prefix + "paths/missing",
            },
            "wrong contact": {
                "kind": "contact_geometry",
                "source_ref": self.prefix + "contacts/missing",
            },
            "wrong component": {
                "kind": "layer_alpha",
                "source_ref": self.prefix + "layers/arm-left/components/1",
            },
            "wrong section": {
                "kind": "contact_geometry",
                "source_ref": self.prefix + "paths/arm.left",
            },
            "wrong kind": {
                "kind": "pose_heatmap",
                "source_ref": self.prefix + "paths/arm.left",
            },
        }
        for label, evidence in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                require_geometry_candidate_binding(
                    candidate_document([evidence]), self.geometry
                )


if __name__ == "__main__":
    unittest.main()
