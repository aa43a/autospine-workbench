"""Deterministic alpha geometry evidence document construction tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.alpha_evidence_document import (  # noqa: E402
    build_alpha_geometry_evidence,
)
from autospine_workbench.alpha_evidence_validation import (  # noqa: E402
    require_valid_alpha_geometry_evidence,
)
from autospine_workbench.limb_candidates import PoseAlphaLimbProvider  # noqa: E402
from autospine_workbench.limb_evidence_layers import load_limb_evidence  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402
from tests.test_limb_candidates import (  # noqa: E402
    TRANSPARENT,
    VISIBLE,
    observations,
    project_fixture,
)


class AlphaEvidenceDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.asset = Path(self.directory.name) / "arm.png"
        rows = [[TRANSPARENT for _ in range(20)] for _ in range(20)]
        for y in range(4, 16):
            for x in range(2, 12):
                rows[y][x] = VISIBLE
        write_rgba(self.asset, rows)
        self.project = project_fixture()
        self.pose = observations()
        self.config = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, self.pose
        ).config

    def build(self, project: dict | None = None, *, provider_version: str = "1") -> dict:
        project = project or self.project
        evidence = load_limb_evidence(
            project,
            {"layer-arm-left": self.asset},
            (100, 100),
            self.config,
        )
        return build_alpha_geometry_evidence(
            project,
            evidence,
            self.pose,
            {"paths": [], "contacts": [], "observability": {}, "qa_flags": ["NO_CONTACT"]},
            config=self.config,
            provider_version=provider_version,
        )

    def test_same_stage_inputs_build_the_same_valid_document(self) -> None:
        first, second = self.build(), self.build()
        self.assertEqual(first, second)
        self.assertEqual(canonical_sha256(first), canonical_sha256(second))
        require_valid_alpha_geometry_evidence(
            first,
            project_id="sample-a",
            joint_ids={"root", "elbow.left", "wrist.left"},
            layer_ids={"layer-arm-left"},
            canvas_width=100,
            canvas_height=100,
        )

    def test_final_decisions_do_not_change_geometry_identity(self) -> None:
        changed = deepcopy(self.project)
        changed["resolved"]["revision"] = 99
        changed["resolved"]["sha256"] = "9" * 64
        changed["resolved"]["joint_decisions"] = {"elbow.left": {"action": "accept"}}
        self.assertEqual(self.build(), self.build(changed))

    def test_semantics_and_provider_version_change_run_identity(self) -> None:
        original = self.build()
        changed = deepcopy(self.project)
        changed["resolved"]["layers"][0]["side"] = "right"
        semantic = self.build(changed)
        versioned = self.build(provider_version="2")
        self.assertNotEqual(
            original["analysis"]["input_sha256"], semantic["analysis"]["input_sha256"]
        )
        self.assertNotEqual(
            original["analysis"]["run_sha256"], versioned["analysis"]["run_sha256"]
        )


if __name__ == "__main__":
    unittest.main()
