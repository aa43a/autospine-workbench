"""Immutable ReviewedMotionBundle v1 contract gates."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_instance_v2_compiler import (  # noqa: E402
    compile_motion_instance_v2,
)
from autospine_workbench.motion_policy_decision import (  # noqa: E402
    build_motion_policy_decision,
)
from autospine_workbench.reviewed_motion_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
    ReviewedMotionBundleContractError,
    build_reviewed_motion_bundle_contract,
    reviewed_motion_bundle_address_sha256,
)
from autospine_workbench.reviewed_motion_policy import (  # noqa: E402
    compile_reviewed_motion_policy,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)


class ReviewedMotionBundleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        fixture = MotionPolicyDecisionFixture(Path(cls.temporary.name))
        decision = build_motion_policy_decision(
            fixture.foot,
            fixture.depth,
            review=approved_review(),
            decisions=fixture.accept_all(),
            root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": False},
        ).document
        policy = compile_reviewed_motion_policy(
            decision, fixture.foot, fixture.depth, fixture.upstream.mesh
        ).document
        base = fixture.upstream.retarget.motion_instance
        target = fixture.upstream.target.document
        v2 = compile_motion_instance_v2(base, target, policy).document
        cls.fixture = fixture
        cls.documents = (fixture.foot, fixture.depth, decision, policy, v2)
        cls.base, cls.target = base, target

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def build(self, documents=None, *, project_id=None, mesh=None, base=None, target=None):
        docs = self.documents if documents is None else documents
        return build_reviewed_motion_bundle_contract(
            project_id or self.fixture.upstream.mesh.project_id,
            *docs,
            mesh or self.fixture.upstream.mesh,
            base or self.base,
            target or self.target,
        )

    def test_deterministic_full_rebuild_and_isolated_access(self):
        first = self.build()
        second = self.build(tuple(deepcopy(row) for row in self.documents))
        self.assertEqual(first.bundle_sha256, second.bundle_sha256)
        self.assertEqual(first.document_bytes, second.document_bytes)
        self.assertEqual(DOCUMENT_NAMES, first.inventory)
        self.assertEqual(7, len(first.identities))
        self.assertEqual(
            first.motion_instance_v2_sha256,
            first.identities["motion_instance_v2_sha256"],
        )
        isolated = first.document_bytes
        isolated[DOCUMENT_NAMES[0]] = b"changed"
        self.assertNotEqual(isolated, first.document_bytes)

    def test_run_manifest_binds_exact_inputs_outputs_and_schema(self):
        contract = self.build()
        run = json.loads(contract.document_bytes["run-manifest.json"])
        self.assertEqual(
            contract.motion_policy_decision_sha256,
            run["inputs"]["motion_policy_decision_sha256"],
        )
        self.assertEqual(
            contract.motion_instance_v2_sha256,
            run["outputs"]["motion_instance_v2_sha256"],
        )
        self.assertEqual(
            self.fixture.upstream.mesh.bundle_sha256,
            run["inputs"]["p3"]["bundle_sha256"],
        )
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is optional")
        schema = json.loads(
            (ROOT / "schemas/reviewed-motion-bundle-run-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        jsonschema.validate(run, schema)

    def test_policy_or_v2_tamper_fails_exact_rebuild(self):
        policy_tamper = list(deepcopy(self.documents))
        policy_tamper[3]["root_correction_keys"][1]["correction_xy_px"][0] += 0.25
        with self.assertRaisesRegex(
            ReviewedMotionBundleContractError, "policy differs"
        ):
            self.build(tuple(policy_tamper))

        v2_tamper = list(deepcopy(self.documents))
        root = next(
            row for row in v2_tamper[4]["tracks"]
            if row["bone_id"] == "root-pelvis"
            and row["property"] == "translation"
        )
        root["keys"][1]["value"][0] += 0.25
        with self.assertRaisesRegex(
            ReviewedMotionBundleContractError, "v2 differs"
        ):
            self.build(tuple(v2_tamper))

    def test_stale_candidate_decision_and_p3_source_fail_closed(self):
        stale_candidate = list(deepcopy(self.documents))
        stale_candidate[0]["summary"]["sample_count"] += 1
        with self.assertRaises(ReviewedMotionBundleContractError):
            self.build(tuple(stale_candidate))

        stale_decision = list(deepcopy(self.documents))
        stale_decision[2]["source"]["foot_lock_candidates_sha256"] = "f" * 64
        with self.assertRaises(ReviewedMotionBundleContractError):
            self.build(tuple(stale_decision))

        spoofed_mesh = replace(
            self.fixture.upstream.mesh, bundle_sha256="e" * 64
        )
        with self.assertRaises(ReviewedMotionBundleContractError):
            self.build(mesh=spoofed_mesh)

    def test_project_or_p5_target_source_mismatch_fails(self):
        with self.assertRaises(ReviewedMotionBundleContractError):
            self.build(project_id="different-project")
        stale_target = deepcopy(self.target)
        stale_target["source"]["p3"]["bundle_sha256"] = "d" * 64
        with self.assertRaises(ReviewedMotionBundleContractError):
            self.build(target=stale_target)

    def test_address_rejects_ordering_and_per_document_limit(self):
        payloads = tuple((name, b"x") for name in DOCUMENT_NAMES)
        v2_sha = hashlib.sha256(b"x").hexdigest()
        with self.assertRaisesRegex(
            ReviewedMotionBundleContractError, "order"
        ):
            reviewed_motion_bundle_address_sha256(
                "project", v2_sha, (payloads[1], payloads[0], *payloads[2:])
            )
        with patch(
            "autospine_workbench.reviewed_motion_bundle_contract.DOCUMENT_LIMITS",
            (0, 1, 1, 1, 1, 1),
        ):
            with self.assertRaisesRegex(
                ReviewedMotionBundleContractError, "byte limit"
            ):
                reviewed_motion_bundle_address_sha256(
                    "project", v2_sha, payloads
                )

    def test_address_rejects_total_limit_and_v2_identity_tamper(self):
        payloads = tuple((name, b"x") for name in DOCUMENT_NAMES)
        v2_sha = hashlib.sha256(b"x").hexdigest()
        with patch(
            "autospine_workbench.reviewed_motion_bundle_contract.MAX_TOTAL_DOCUMENT_BYTES",
            5,
        ):
            with self.assertRaisesRegex(
                ReviewedMotionBundleContractError, "total byte limit"
            ):
                reviewed_motion_bundle_address_sha256(
                    "project", v2_sha, payloads
                )
        with self.assertRaisesRegex(
            ReviewedMotionBundleContractError, "differ from their address"
        ):
            reviewed_motion_bundle_address_sha256(
                "project", "0" * 64, payloads
            )


if __name__ == "__main__":
    unittest.main()
