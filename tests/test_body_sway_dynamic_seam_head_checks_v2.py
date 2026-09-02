"""Direct current-head replay tests for the P10.5d v2 fence."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_dynamic_seam_head_checks_v2 import (  # noqa: E402
    BodySwayDynamicSeamHeadCheckV2Error,
    require_current_body_sway_dynamic_seam_heads_v2,
)
from autospine_workbench.body_sway_visual_review_application_v2 import (  # noqa: E402
    BodySwayVisualReviewApplicationV2,
)
from autospine_workbench.layer_manifest import (  # noqa: E402
    LayerManifestBundleStore,
)
from autospine_workbench.mesh_bundle_reader import (  # noqa: E402
    VerifiedMeshBundleReader,
)
from autospine_workbench.mesh_bundle_store import MeshBundleStore  # noqa: E402
from autospine_workbench.mesh_pipeline import VerifiedMeshPipeline  # noqa: E402
from autospine_workbench.project_store import ProjectStore  # noqa: E402
from autospine_workbench.region_rig import compile_region_rig  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.reviewed_seam_anchor_set_compiler import (  # noqa: E402
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.rig_bundle import RigBundleStore  # noqa: E402
from autospine_workbench.seam_anchor_review_address import (  # noqa: E402
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application import (  # noqa: E402
    SeamAnchorReviewApplication,
)
from autospine_workbench.seam_anchor_review_candidate_binding import (  # noqa: E402
    load_bound_seam_anchor_review_candidate,
)
from autospine_workbench.seam_anchor_review_history import (  # noqa: E402
    load_seam_anchor_review_decision,
)
from tests.body_sway_visual_review_v2_helpers import (  # noqa: E402
    fake_runtime_profile_v2,
)
from tests.p10_candidate_helpers import _resolved_for_project  # noqa: E402
from tests.p10_review_admission_v2_helpers import (  # noqa: E402
    P10ReviewAdmissionV2State,
    shared_p10_review_admission_v2_fixture,
)
from tests.resolved_snapshot_helpers import (  # noqa: E402
    refresh_resolved_snapshot,
)
from tests.seam_anchor_review_helpers import seam_review_rows  # noqa: E402
from tests.test_seam_anchor_review_http_evidence_e2e import (  # noqa: E402
    _manifest_and_assets,
)
from tests.test_verified_mesh_compiler import _probes  # noqa: E402


HEAD = "autospine_workbench.body_sway_dynamic_seam_head_checks_v2."
VISUAL_COMMAND = (
    "autospine_workbench.p10_review_admission_v2_commands."
    "resolve_p10_visual_review_v2_context"
)


class _SeamFixture:
    def __init__(self, root: Path, state_root: Path, project_id: str) -> None:
        manifest, assets, sizes = _manifest_and_assets(
            root / "seam-assets",
        )
        manifest["project_id"] = project_id
        resolved = _resolved_for_project()
        resolved["project_id"] = project_id
        resolved = refresh_resolved_snapshot(resolved)
        compiled = compile_region_rig(
            manifest, resolved,
            layer_manifest_sha256=canonical_sha256(manifest),
            image_sizes=sizes,
        )
        layers, manifest_sha = LayerManifestBundleStore(
            state_root,
        ).publish(project_id, manifest, assets)
        rig_path, rig_sha = RigBundleStore(state_root).publish(
            project_id, compiled.rig, compiled.run_manifest,
            _probes(project_id, compiled.rig, compiled.run_manifest), layers,
        )
        mesh_result = VerifiedMeshPipeline(state_root).build(
            project_id, rig_sha, rig_path.name,
        )
        mesh_address = MeshBundleStore(state_root).publish(
            project_id, mesh_result.rig, mesh_result.run_manifest,
            mesh_result.probes, mesh_result.visuals, mesh_result.pngs,
        )
        mesh = VerifiedMeshBundleReader(state_root).load(
            project_id, mesh_address.rig_sha256,
            mesh_address.bundle_sha256,
        )
        self.address = ExactSeamAnchorReviewAddress(
            project_id, manifest_sha, mesh.rig_sha256, mesh.bundle_sha256,
        )
        application = SeamAnchorReviewApplication(state_root)
        prepared = application.prepare(self.address)
        submitted = application.submit(
            self.address, _seam_payload(prepared, "current v1 seam head"),
        )
        bound = load_bound_seam_anchor_review_candidate(
            state_root, self.address,
        )
        decision = load_seam_anchor_review_decision(
            state_root, self.address, bound.candidates.sha256,
            submitted.decision_sha256, candidates=bound.candidates,
            rig=bound.rig,
        )
        self.reviewed = compile_reviewed_seam_anchor_set(
            bound.candidates.document, decision.document, bound.rig,
        )
        self.candidate_sha256 = bound.candidates.sha256
        self.revision = submitted.revision
        self.decision_sha256 = submitted.decision_sha256


def _seam_payload(prepared, notes):
    return {
        "base_revision": prepared.history.current_revision,
        "candidate_sha256": prepared.candidate_sha256,
        "previous_decision_sha256":
            prepared.history.head_decision_sha256,
        "review": {"reviewer_id": "p10-v2-head-test", "notes": notes},
        "decisions": seam_review_rows(
            prepared.candidate_document, "accept",
        ),
    }


def _source(visual, seam):
    admission = visual.admission.document
    return {
        "project_id": admission["project_id"],
        "source_set_sha256": canonical_sha256({"fixture": "p10.5d-v2"}),
        "body_sway_continuous_preview_proof_v2": {
            "project_id": admission["project_id"], "clip_id": "idle",
            "source": {"amplitude_envelope_candidate_v2": {
                "source": {
                    "review_admission_v2_sha256": visual.admission.sha256,
                    "review_admission_v2": admission,
                },
            }},
        },
        "reviewed_seam_anchor_set_v1_sha256": seam.reviewed.sha256,
        "reviewed_seam_anchor_set_v1": seam.reviewed.document,
    }


class BodySwayDynamicSeamHeadChecksV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.visual = shared_p10_review_admission_v2_fixture()
        cls.base_temporary = tempfile.TemporaryDirectory()
        root = Path(cls.base_temporary.name)
        state = cls.visual.copy_state(root)
        cls.seam = _SeamFixture(
            root, state.state_root, cls.visual.admission.document["project_id"],
        )
        cls.base_state = state.state_root
        cls.source = _source(cls.visual, cls.seam)

    @classmethod
    def tearDownClass(cls):
        cls.base_temporary.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.state_root = root / "state"
        shutil.copytree(self.base_state, self.state_root)
        self.store = ProjectStore(
            root / "workspace", state_root=self.state_root,
            measure_composite_quality=False,
        )
        self.reader = SimpleNamespace(get=lambda _job_id: {})

    def tearDown(self):
        self.temporary.cleanup()

    @contextmanager
    def current_context(self):
        with ExitStack() as stack:
            stack.enter_context(patch(
                HEAD + "require_body_sway_dynamic_seam_source_v2",
                side_effect=lambda value: deepcopy(value),
            ))
            stack.enter_context(patch(
                VISUAL_COMMAND, return_value=self.visual.context,
            ))
            stack.enter_context(fake_runtime_profile_v2())
            yield

    @contextmanager
    def seam_context(self, *, admission_sha256=None):
        expected = admission_sha256 or self.visual.admission.sha256
        with patch(
            HEAD + "require_body_sway_dynamic_seam_source_v2",
            side_effect=lambda value: deepcopy(value),
        ), patch(
            HEAD + "require_current_body_sway_review_admission_v2",
            return_value=SimpleNamespace(admission_sha256=expected),
        ):
            yield

    def test_real_visual_recompile_and_seam_double_snapshot_match(self):
        from autospine_workbench \
            import body_sway_dynamic_seam_head_checks_v2 as module

        with self.current_context(), patch(
            HEAD + "require_current_body_sway_review_admission_v2",
            wraps=module.require_current_body_sway_review_admission_v2,
        ) as visual, patch(
            HEAD + "prepare_current_head_reviewed_seam_anchor_set",
            wraps=module.prepare_current_head_reviewed_seam_anchor_set,
        ) as seam:
            observation = require_current_body_sway_dynamic_seam_heads_v2(
                self.reader, self.store, self.source,
            )
        self.assertEqual("compile_time", observation.document["scope"])
        self.assertFalse(observation.document["permanent_authority_claimed"])
        self.assertEqual(1, visual.call_count)
        self.assertEqual(1, seam.call_count)

    def test_stale_visual_decision_is_rejected(self):
        visual_state = P10ReviewAdmissionV2State(
            self.state_root, self.store,
            BodySwayVisualReviewApplicationV2(self.state_root),
        )
        self.visual.append(visual_state, "approve")
        with self.current_context(), self.assertRaises(
            BodySwayDynamicSeamHeadCheckV2Error
        ):
            require_current_body_sway_dynamic_seam_heads_v2(
                self.reader, self.store, self.source,
            )

    def test_stale_seam_decision_is_rejected(self):
        application = SeamAnchorReviewApplication(self.state_root)
        prepared = application.prepare(self.seam.address)
        application.submit(
            self.seam.address, _seam_payload(prepared, "new seam head"),
        )
        with self.seam_context(), self.assertRaises(
            BodySwayDynamicSeamHeadCheckV2Error
        ):
            require_current_body_sway_dynamic_seam_heads_v2(
                self.reader, self.store, self.source,
            )

    def test_candidate_manifest_and_p3_crosswires_fail_closed(self):
        fields = (
            "seam_anchor_candidate_sha256", "layer_manifest_sha256",
            "p3_rig_sha256", "p3_bundle_sha256",
        )
        for index, field in enumerate(fields):
            source = deepcopy(self.source)
            source["reviewed_seam_anchor_set_v1"]["source"][field] = (
                f"{index + 1:x}" * 64
            )
            with self.subTest(field=field), self.seam_context(), \
                    self.assertRaises(BodySwayDynamicSeamHeadCheckV2Error):
                require_current_body_sway_dynamic_seam_heads_v2(
                    self.reader, self.store, source,
                )

    def test_visual_admission_digest_crosswire_fails_after_replay(self):
        source = deepcopy(self.source)
        amplitude = source["body_sway_continuous_preview_proof_v2"] \
            ["source"]["amplitude_envelope_candidate_v2"]["source"]
        amplitude["review_admission_v2_sha256"] = "f" * 64
        with self.seam_context(admission_sha256="e" * 64), self.assertRaises(
            BodySwayDynamicSeamHeadCheckV2Error
        ):
            require_current_body_sway_dynamic_seam_heads_v2(
                self.reader, self.store, source,
            )


if __name__ == "__main__":
    unittest.main()
