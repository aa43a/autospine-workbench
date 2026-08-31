"""Package-centric exact replay tests for the P10.3 Preview v2 service."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.capture_framing_decision import (
    build_capture_framing_decision,
)
from autospine_workbench.capture_framing_history import (
    CaptureFramingHistorySnapshot,
    publish_capture_framing_decision,
)
from autospine_workbench.capture_framing_verified_head import (
    CaptureFramingVerifiedHead,
)
from autospine_workbench.current_project_chain import CurrentProjectChain
from autospine_workbench.depth_pair_policy import depth_pair_policy_sha256
from autospine_workbench.idle_behavior_candidates import (
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_decision import (
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_review_head import (
    read_idle_behavior_review_head,
)
from autospine_workbench.idle_behavior_review_packages import (
    list_idle_behavior_review_packages,
)
from autospine_workbench.idle_behavior_review_replay import (
    replay_idle_behavior_review_package,
)
from autospine_workbench.idle_behavior_review_store import (
    IdleBehaviorReviewStore,
)
from autospine_workbench.motion_instance_v2_compiler import (
    compile_motion_instance_v2,
)
from autospine_workbench.motion_policy_decision import (
    build_motion_policy_decision,
)
from autospine_workbench.p10_preview_v2_commands import (
    P10PreviewV2CommandError,
    compile_body_sway_preview_v2_for_package,
    require_exact_preview_v2_for_mount,
)
from autospine_workbench.p10_preview_v2_cache import (
    clear_p10_preview_v2_cache,
)
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.reviewed_motion_bundle_store import (
    ReviewedMotionBundleStore,
)
from autospine_workbench.reviewed_motion_bundle_upstream import (
    require_reviewed_motion_upstreams,
)
from autospine_workbench.reviewed_motion_policy import (
    compile_reviewed_motion_policy,
)
from autospine_workbench.body_sway_probe_inputs import (
    require_body_sway_probe_inputs,
)
from autospine_workbench.body_sway_probe_report import (
    compile_body_sway_probe_report,
)
from autospine_workbench.body_sway_remediation_analysis import (
    compile_body_sway_remediation_analysis,
)
from autospine_workbench.capture_framing_candidate import (
    compile_capture_framing_candidate,
)
from autospine_workbench.temporary_body_sway_preview_v2 import (
    TemporaryBodySwayPreviewV2,
)
from tests.idle_behavior_decision_helpers import (
    adjust_decision,
    completed_review,
)
from tests.motion_policy_decision_helpers import approved_review
from tests.motion_policy_review_package_helpers import write_review_package
from tests.p10_candidate_documents import build_reviewed_documents
from tests.p10_candidate_helpers import (
    P10PersistedFixture,
    _manifest as persisted_manifest,
)


def _edge_manifest(asset: Path):
    """Keep setup in-canvas while making reviewed sway cross its edge."""

    document = persisted_manifest(asset)
    for layer in document["layers"]:
        if layer["rig_hint"]["candidate_bone"] != "neck-head":
            continue
        layer["raster"]["crop_bbox_xywh"][0] = 380
        layer["raster"]["canvas_offset_xy"][0] = 380
        layer["rig_hint"]["pivot"]["xy"][0] = 390
    return document


class _PackageFixture:
    """Persist one real P3/P5/P9 package and both P10 review heads."""

    def __init__(self, root: Path) -> None:
        self.root = root
        with patch(
            "tests.p10_candidate_helpers._manifest",
            side_effect=_edge_manifest,
        ):
            self.persisted = P10PersistedFixture(root)
        self.state = self.persisted.state
        reviewed = self._publish_coherent_p9()
        self._write_audit_stub(reviewed.project_id)
        self.store = ProjectStore(root / "workspace", state_root=self.state)
        self.current = {
            reviewed.project_id: CurrentProjectChain(
                reviewed.project_id,
                self.persisted.mesh.resolved_project_sha256,
                self.persisted.mesh.layer_manifest_sha256,
            ),
        }
        inventory = list_idle_behavior_review_packages(
            self.state,
            project_ids=(reviewed.project_id,),
            current_project_chains=self.current,
        )
        self.package_id = inventory["recommended_package_id"]
        if not isinstance(self.package_id, str):
            raise AssertionError("fixture package must be uniquely current")
        evidence = replay_idle_behavior_review_package(
            self.state,
            next(address for address in (
                self._address(),
            )),
        )
        candidates = evidence.candidates.document
        adjustment = adjust_decision(candidates)
        for row in adjustment["payload"]["per_bone_amplitude_deg"]:
            row["value"] = 10.0
        decision = build_idle_behavior_decision(
            candidates,
            review=completed_review(),
            decisions=[adjustment],
        )
        IdleBehaviorReviewStore(self.state).publish(
            decision, candidates,
            base_revision=0, previous_decision_sha256=None,
        )
        inputs = require_body_sway_probe_inputs(
            evidence.manifest, candidates, decision.document,
            evidence.mesh_bundle, evidence.retarget_bundle,
            evidence.reviewed_contract,
        )
        report = compile_body_sway_probe_report(inputs)
        viewport = compile_body_sway_remediation_analysis(
            inputs, report,
        ).dynamic_viewport
        self.framing_candidate = compile_capture_framing_candidate(
            inputs, report, viewport,
            read_idle_behavior_review_head(self.state, candidates),
            package_id=self.package_id,
        )
        self.framing_decision = build_capture_framing_decision(
            self.framing_candidate,
            action="accept",
            world_viewport=None,
            reason_code="human-approved-automatic-capture-framing-v1",
            revision=1,
            supersedes_decision_sha256=None,
        )
        publish_capture_framing_decision(
            self.state, self.framing_decision, self.framing_candidate,
            base_revision=0, previous_decision_sha256=None,
        )

    def _address(self):
        from autospine_workbench.idle_behavior_review_packages import (
            require_current_idle_behavior_review_address,
        )
        return require_current_idle_behavior_review_address(
            self.state, self.package_id,
            project_ids=(self.persisted.mesh.project_id,),
            current_project_chains=self.current,
        )

    def _publish_coherent_p9(self):
        mesh, retarget = self.persisted.mesh, self.persisted.retarget
        foot, depth, _decision, _policy, _v2 = build_reviewed_documents(
            mesh, retarget,
        )
        depth = deepcopy(depth)
        slots = sorted(mesh.rig["slots"], key=lambda row: row["id"])[:2]
        roles = {
            row["bone_id"]: row["role"]
            for row in retarget.target_profile["bones"]
        }
        pair_slots = sorted(({
            "slot_id": row["id"], "depth_role": roles[row["bone"]],
        } for row in slots), key=lambda row: row["slot_id"])
        setup_front = max(slots, key=lambda row: row["setup_draw_order"])["id"]
        pair = depth["pairs"][0]
        pair["slots"] = pair_slots
        pair["setup_front_slot"] = setup_front
        for sample in pair["samples"]:
            sample["scores"] = [{
                **row,
                "midpoint_depth_root_relative_normalized": 0.0,
                "front_score": 0.0,
            } for row in pair_slots]
            sample["current_front_slot"] = setup_front
        policy = {
            "format": "autospine-depth-pair-policy",
            "format_version": 1,
            "policy_id": "preview-v2-depth-v1",
            "project_id": depth["project_id"],
            "clip_id": depth["clip_id"],
            "source": deepcopy({
                stage: depth["source"][stage] for stage in ("p8", "p5", "p3")
            }),
            "review": {"status": "approved", "method": "human"},
            "hysteresis": deepcopy(depth["hysteresis"]),
            "pairs": [{
                key: deepcopy(pair[key])
                for key in ("pair_id", "slots", "setup_front_slot")
            }],
        }
        depth["source"]["depth_pair_policy_sha256"] = (
            depth_pair_policy_sha256(policy)
        )
        decision = build_motion_policy_decision(
            foot, depth,
            review=approved_review(), decisions=[], root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": False},
        ).document
        reviewed_policy = compile_reviewed_motion_policy(
            decision, foot, depth, mesh,
        ).document
        base, target = require_reviewed_motion_upstreams(mesh, retarget)
        v2 = compile_motion_instance_v2(base, target, reviewed_policy).document
        published = ReviewedMotionBundleStore(self.state).publish(
            mesh.project_id, foot, depth, decision, reviewed_policy, v2,
            mesh, retarget,
        )
        write_review_package(
            self.state, policy, foot, depth, motion_id="preview-v2",
        )
        from autospine_workbench.reviewed_motion_bundle_reader import (
            VerifiedReviewedMotionBundleReader,
        )
        return VerifiedReviewedMotionBundleReader(self.state).load(
            mesh.project_id, published.motion_instance_v2_sha256,
            published.bundle_sha256, mesh_bundle=mesh,
            retarget_bundle=retarget,
        )

    def _write_audit_stub(self, project_id: str) -> None:
        directory = (
            self.root / "workspace" / "tmp" / "psd_audit" / "results"
            / project_id
        )
        directory.mkdir(parents=True)
        (directory / "audit.json").write_text("{}", encoding="utf-8")

    @contextmanager
    def current_chains(self, *, value=None):
        with patch(
            "autospine_workbench.p10_preview_v2_service."
            "rebuild_current_project_chains",
            return_value=self.current if value is None else value,
        ):
            yield


class P10PreviewV2CommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = _PackageFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        clear_p10_preview_v2_cache()

    def test_current_projectstore_package_compiles_and_mount_replays(self):
        with self.fixture.current_chains():
            result = compile_body_sway_preview_v2_for_package(
                self.fixture.store, self.fixture.package_id,
            )
            mounted = require_exact_preview_v2_for_mount(result)
        self.assertEqual(self.fixture.package_id, result.package_id)
        self.assertEqual(result.temporary_preview_v2_sha256, mounted.sha256)
        self.assertEqual(1, result.capture_framing_revision)
        self.assertTrue(result.case_count)
        self.assertNotIn(str(self.fixture.root), repr(result))

    def test_repeated_prepare_and_mount_revalidate_without_recompile(self):
        from autospine_workbench.p10_preview_v2_service import _compile_record

        with self.fixture.current_chains(), patch(
            "autospine_workbench.p10_preview_v2_service._compile_record",
            wraps=_compile_record,
        ) as compiler:
            result = compile_body_sway_preview_v2_for_package(
                self.fixture.store, self.fixture.package_id,
            )
            repeated = compile_body_sway_preview_v2_for_package(
                self.fixture.store, self.fixture.package_id,
            )
            mounted = require_exact_preview_v2_for_mount(result)
        self.assertEqual(1, compiler.call_count)
        self.assertIs(result, repeated)
        self.assertEqual(result.temporary_preview_v2_sha256, mounted.sha256)

    def test_missing_capture_framing_head_fails_closed(self):
        empty = CaptureFramingVerifiedHead(
            self.fixture.framing_candidate.sha256,
            CaptureFramingHistorySnapshot(0, None, None, None),
            None,
        )
        with self.fixture.current_chains(), patch(
            "autospine_workbench.p10_preview_v2_service."
            "read_capture_framing_verified_head",
            return_value=empty,
        ), self.assertRaisesRegex(
            P10PreviewV2CommandError, "no approved CaptureFraming head",
        ):
            compile_body_sway_preview_v2_for_package(
                self.fixture.store, self.fixture.package_id,
            )

    def test_historical_package_is_never_admitted(self):
        stale = {
            self.fixture.persisted.mesh.project_id: CurrentProjectChain(
                self.fixture.persisted.mesh.project_id,
                self.fixture.persisted.mesh.resolved_project_sha256,
                "f" * 64,
            ),
        }
        with self.fixture.current_chains(value=stale), self.assertRaisesRegex(
            P10PreviewV2CommandError, "Historical.*read-only",
        ):
            compile_body_sway_preview_v2_for_package(
                self.fixture.store, self.fixture.package_id,
            )

    def test_mount_rejects_replayed_framing_head_drift(self):
        with self.fixture.current_chains():
            result = compile_body_sway_preview_v2_for_package(
                self.fixture.store, self.fixture.package_id,
            )
        changed = replace(
            result,
            capture_framing_decision_sha256="f" * 64,
            capture_framing_revision=result.capture_framing_revision + 1,
        )
        with patch(
            "autospine_workbench.p10_preview_v2_commands."
            "compile_body_sway_preview_v2_for_package",
            return_value=changed,
        ), self.assertRaisesRegex(
            P10PreviewV2CommandError,
            "capture_framing_decision_sha256 changed",
        ):
            require_exact_preview_v2_for_mount(result)

    def test_mount_rejects_cached_preview_byte_divergence(self):
        with self.fixture.current_chains():
            result = compile_body_sway_preview_v2_for_package(
                self.fixture.store, self.fixture.package_id,
            )
        artifacts = result.artifact_bytes
        first = sorted(artifacts)[0]
        artifacts[first] += b"tampered-after-command"
        forged = TemporaryBodySwayPreviewV2(
            result._preview.canonical_bytes.decode("utf-8"),
            tuple(sorted(artifacts.items())),
        )
        with self.fixture.current_chains(), self.assertRaisesRegex(
            P10PreviewV2CommandError, "bytes changed during mount replay",
        ):
            require_exact_preview_v2_for_mount(
                replace(result, _preview=forged),
            )


if __name__ == "__main__":
    unittest.main()
