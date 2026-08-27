"""Real persisted-chain fixtures for P10.6a end-to-end tests."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
from pathlib import Path
from unittest.mock import patch

from autospine_workbench.p10_continuous_proof_commands import (
    compile_body_sway_continuous_proof_command,
)
from autospine_workbench.p10_dynamic_seam_commands import (
    compile_body_sway_dynamic_seam_probe_command,
)
from autospine_workbench.reviewed_seam_anchor_set_bundle_store import (
    ReviewedSeamAnchorSetBundleStore,
)
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application import (
    SeamAnchorReviewApplication,
)
from autospine_workbench.seam_anchor_review_candidate_binding import (
    load_bound_seam_anchor_review_candidate,
)
from autospine_workbench.seam_anchor_review_history import (
    load_seam_anchor_review_decision,
)
from autospine_workbench.seam_anchor_review_json import canonical_json_bytes
from tests.body_sway_dynamic_seam_analysis_helpers import certified_proof
from tests.body_sway_runtime_capture_helpers import fake_runtime_profile
from tests.p10_review_admission_helpers import P10ReviewAdmissionFixture
from tests.p10_candidate_helpers import (
    _resolved_for_project as _base_resolved_for_project,
)
from tests.seam_anchor_review_helpers import seam_review_rows
from tests.test_seam_anchor_review_http_evidence_e2e import _layer


BACKEND = (
    "autospine_workbench.body_sway_dynamic_seam_analysis."
    "prove_body_sway_dynamic_seam_sampled_linear_segment"
)


class MotionConsumerE2EFixture:
    """One exact P3/P5/P9, visual-review, and seam-review state tree."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        with ExitStack() as stack:
            stack.enter_context(patch(
                "tests.p10_candidate_helpers._manifest",
                side_effect=_seam_capable_manifest,
            ))
            stack.enter_context(patch(
                "tests.p10_candidate_helpers._resolved_for_project",
                side_effect=_seam_capable_resolved,
            ))
            self.visual = P10ReviewAdmissionFixture(self.root)
        self.state_root = self.visual.state_root
        self.project_id = self.visual.address.project_id
        self.seam_address = self._seam_address()
        self.seam_application = SeamAnchorReviewApplication(self.state_root)
        self.seam_submission = self._submit_seam_review("initial approval")
        self.reviewed_set = self._publish_reviewed_set()
        self.continuous_proof = self._compile_continuous_proof()
        self.continuous_proof_path = self._write_document(
            "continuous-proof.json", self.continuous_proof.document
        )

    def compile_dynamic_probe(self):
        return compile_body_sway_dynamic_seam_probe_command(
            self.state_root,
            self.project_id,
            self.continuous_proof_path,
            reviewed_set_sha256=self.reviewed_set.set_sha256,
            reviewed_set_bundle_sha256=self.reviewed_set.bundle_sha256,
        )

    def write_probe(self, probe: dict) -> Path:
        return self._write_document("dynamic-seam-probe.json", probe)

    def advance_visual_head(self) -> None:
        self.visual.append("reject")

    def advance_seam_head(self) -> None:
        self._submit_seam_review("superseding approval")

    @contextmanager
    def deterministic_dynamic_seam_backend(self):
        def prove(locators, _context, left, right, *, budget):
            return certified_proof(
                locators, left.tick, right.tick,
                boxes=min(1, budget.max_boxes),
            )

        with ExitStack() as stack:
            stack.enter_context(fake_runtime_profile())
            stack.enter_context(patch(BACKEND, side_effect=prove))
            yield

    def _seam_address(self) -> ExactSeamAnchorReviewAddress:
        source = self.visual.command_kwargs
        return ExactSeamAnchorReviewAddress(
            self.project_id,
            source["layer_manifest_sha256"],
            source["p3_rig_sha256"],
            source["p3_bundle_sha256"],
        )

    def _submit_seam_review(self, notes: str):
        prepared = self.seam_application.prepare(self.seam_address)
        payload = {
            "base_revision": prepared.history.current_revision,
            "candidate_sha256": prepared.candidate_sha256,
            "previous_decision_sha256": (
                prepared.history.head_decision_sha256
            ),
            "review": {"reviewer_id": "e2e-reviewer", "notes": notes},
            "decisions": seam_review_rows(
                prepared.candidate_document, "accept"
            ),
        }
        return self.seam_application.submit(self.seam_address, payload)

    def _publish_reviewed_set(self):
        bound = load_bound_seam_anchor_review_candidate(
            self.state_root, self.seam_address
        )
        decision = load_seam_anchor_review_decision(
            self.state_root,
            self.seam_address,
            bound.candidates.sha256,
            self.seam_submission.decision_sha256,
            candidates=bound.candidates,
            rig=bound.rig,
        )
        reviewed = compile_reviewed_seam_anchor_set(
            bound.candidates.document, decision.document, bound.rig
        )
        return ReviewedSeamAnchorSetBundleStore(self.state_root).publish(
            bound.candidates, decision, bound.rig, reviewed
        )

    def _compile_continuous_proof(self):
        with fake_runtime_profile():
            return compile_body_sway_continuous_proof_command(
                *self.visual.command_args, **self.visual.command_kwargs
            )

    def _write_document(self, name: str, document: dict) -> Path:
        path = self.root / "e2e-inputs" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(canonical_json_bytes(document))
        return path


def _seam_capable_manifest(asset: Path) -> dict:
    """Replace the compact preview art with eight seam-capable regions."""

    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    specs = (
        ("torso", "body.torso", "center", (190, 220), "spine-chest"),
        ("pelvis", "body.pelvis", "bilateral", (190, 330), "root-pelvis"),
        ("arm.left", "body.arm.upper", "left", (205, 225), "upper-arm.left"),
        ("arm.right", "body.arm.upper", "right", (175, 225), "upper-arm.right"),
        ("leg.left", "body.leg", "left", (205, 345), "thigh.left"),
        ("leg.right", "body.leg", "right", (175, 345), "thigh.right"),
        ("foot.left", "body.foot", "left", (205, 365), "calf.left"),
        ("foot.right", "body.foot", "right", (175, 365), "calf.right"),
    )
    layers = [
        _layer(identifier, role, side, offset, (20, 30), bone, order, digest)
        for order, (identifier, role, side, offset, bone) in enumerate(specs)
    ]
    for layer in layers:
        layer["raster"]["canvas_size"] = [400, 512]
    return {
        "format": "autospine-layer-manifest",
        "format_version": 1,
        "project_id": "p10-persisted",
        "revision": 1,
        "source": {
            "psd_sha256": "a" * 64,
            "audit_sha256": "b" * 64,
            "canvas": [400, 512],
            "coordinate_system": {
                "origin": "top_left", "x_axis": "right", "y_axis": "down",
                "units": "pixel", "side_naming": "character_side",
                "view_orientation": "front", "mirror_state": "not_mirrored",
            },
        },
        "layers": layers,
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def _seam_capable_resolved() -> dict:
    value = _base_resolved_for_project()
    value["canvas"]["height"] = 512
    value.pop("sha256")
    value["sha256"] = canonical_sha256(value)
    return value
