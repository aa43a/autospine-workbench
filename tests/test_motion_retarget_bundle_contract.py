"""Immutable P5 retarget bundle contract tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.motion_mesh_regression import (  # noqa: E402
    build_motion_mesh_regression,
)
from autospine_workbench.motion_mesh_regression_validation import (  # noqa: E402
    MotionMeshRegressionShapeError,
    require_motion_mesh_regression_shape,
)
from autospine_workbench.motion_retarget_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
    MotionRetargetBundleContractError,
    build_motion_retarget_bundle_contract,
    retarget_bundle_address_sha256,
)
from autospine_workbench.motion_retarget_compiler import (  # noqa: E402
    compile_motion_instance,
)
from autospine_workbench.motion_retarget_report import (  # noqa: E402
    build_motion_retarget_report,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.test_motion_bundle_contract import payload  # noqa: E402
from tests.test_motion_mesh_regression import (  # noqa: E402
    calf_bend_instance,
    exact_mesh_and_target,
)


def canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


class MotionRetargetBundleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        state = Path(self.temporary.name) / "state"
        self.mesh, self.profile = exact_mesh_and_target(converted=False)
        published = MotionBundleStore(state).publish(*payload("idle"))
        self.motion = VerifiedMotionBundleReader(state).load(
            published.clip_sha256, published.bundle_sha256
        )
        self.retargeted = compile_motion_instance(self.motion, self.profile)
        self.report = build_motion_retarget_report(
            self.motion, self.profile, self.retargeted
        )
        self.mesh_report = build_motion_mesh_regression(
            self.retargeted.instance, self.profile.document, self.mesh
        )
        self.arguments = [
            self.profile.document["project_id"],
            self.profile.document,
            self.retargeted.instance,
            self.retargeted.run,
            self.report.document,
            self.mesh_report.document,
        ]

    def build(self, arguments=None):
        return build_motion_retarget_bundle_contract(
            *(self.arguments if arguments is None else arguments)
        )

    def test_success_has_fixed_canonical_inventory_and_exact_identities(self):
        contract = self.build()
        self.assertEqual(DOCUMENT_NAMES, contract.inventory)
        self.assertEqual(self.profile.document["project_id"], contract.project_id)
        self.assertEqual("idle", contract.clip_id)
        self.assertEqual(self.profile.sha256, contract.target_profile_sha256)
        self.assertEqual(self.retargeted.instance_sha256, contract.instance_sha256)
        self.assertEqual(self.report.sha256, contract.report_sha256)
        self.assertEqual(self.mesh_report.sha256, contract.mesh_report_sha256)
        self.assertEqual(
            self.retargeted.run_document_sha256,
            contract.run_document_sha256,
        )
        documents = contract.document_bytes
        for name in DOCUMENT_NAMES:
            self.assertEqual(
                documents[name], canonical(json.loads(documents[name]))
            )

    def test_contract_is_deterministic_frozen_and_document_map_is_isolated(self):
        first, second = self.build(), self.build()
        self.assertEqual(first, second)
        documents = first.document_bytes
        documents.clear()
        self.assertEqual(DOCUMENT_NAMES, first.inventory)
        with self.assertRaises(FrozenInstanceError):
            first.project_id = "other"  # type: ignore[misc]

    def test_unknown_fields_fail_closed(self):
        arguments = deepcopy(self.arguments)
        arguments[4]["latest"] = True
        with self.assertRaises(MotionRetargetBundleContractError):
            self.build(arguments)

        mesh = self.mesh_report.document
        mesh["unexpected"] = []
        with self.assertRaises(MotionMeshRegressionShapeError):
            require_motion_mesh_regression_shape(mesh)

    def test_nonfinite_evidence_fails_before_addressing(self):
        arguments = deepcopy(self.arguments)
        arguments[4]["finite_pose"]["max_abs_rotation_deg"] = math.nan
        with self.assertRaises(MotionRetargetBundleContractError):
            self.build(arguments)

        mesh = self.mesh_report.document
        mesh["sample_count"] = math.inf
        with self.assertRaises(MotionMeshRegressionShapeError):
            require_motion_mesh_regression_shape(mesh)
        mesh["sample_count"] = 50_001
        with self.assertRaises(MotionMeshRegressionShapeError):
            require_motion_mesh_regression_shape(mesh)

    def test_mesh_status_cannot_hide_unsafe_worst_metrics(self):
        converted_mesh, converted_profile = exact_mesh_and_target(converted=True)
        converted_instance = compile_motion_instance(
            self.motion, converted_profile
        ).instance
        baseline = build_motion_mesh_regression(
            converted_instance, converted_profile.document, converted_mesh
        ).document
        mesh = deepcopy(baseline)
        mesh["attachments"][0]["worst"]["max_flipped_count"] = 1
        with self.assertRaisesRegex(
            MotionMeshRegressionShapeError, "differs from its worst metrics"
        ):
            require_motion_mesh_regression_shape(mesh)

        mesh = deepcopy(baseline)
        worst = mesh["attachments"][0]["worst"]
        worst["min_signed_area_ratio"] = 2.0
        worst["max_signed_area_ratio"] = 1.0
        with self.assertRaisesRegex(
            MotionMeshRegressionShapeError, "range is inverted"
        ):
            require_motion_mesh_regression_shape(mesh)

    def test_instance_tamper_breaks_run_output_binding(self):
        arguments = deepcopy(self.arguments)
        key = arguments[2]["tracks"][0]["keys"][1]
        if isinstance(key["value"], list):
            key["value"][0] += 0.25
        else:
            key["value"] += 0.25
        with self.assertRaises(MotionRetargetBundleContractError):
            self.build(arguments)

    def test_valid_rejected_mesh_diagnostic_cannot_be_published(self):
        mesh, profile = exact_mesh_and_target(converted=True, failing=True)
        instance = calf_bend_instance(profile, angle=90.0)
        rejected = build_motion_mesh_regression(
            instance, profile.document, mesh
        ).document
        self.assertEqual("rejected", rejected["status"])
        require_motion_mesh_regression_shape(rejected)
        arguments = [*self.arguments[:-1], rejected]
        with self.assertRaisesRegex(
            MotionRetargetBundleContractError, "cannot enter"
        ):
            self.build(arguments)

    def test_report_and_mesh_identity_drift_fail_closed(self):
        mutations = (
            lambda args: args[4]["source"].update(instance_sha256="f" * 64),
            lambda args: args[4]["source"].update(
                retarget_run_document_sha256="f" * 64
            ),
            lambda args: args[5]["source"].update(p3_rig_sha256="f" * 64),
            lambda args: args[5]["source"].update(
                target_profile_sha256="f" * 64
            ),
        )
        for mutate in mutations:
            arguments = deepcopy(self.arguments)
            mutate(arguments)
            with self.subTest(mutate=mutate), self.assertRaises(
                MotionRetargetBundleContractError
            ):
                self.build(arguments)

    def test_address_is_sensitive_and_rejects_noncanonical_inventory(self):
        contract = self.build()
        items = tuple(
            (name, contract.document_bytes[name]) for name in DOCUMENT_NAMES
        )
        baseline = contract.bundle_sha256
        self.assertNotEqual(
            baseline,
            retarget_bundle_address_sha256("other", contract.clip_id, items),
        )
        self.assertNotEqual(
            baseline,
            retarget_bundle_address_sha256(contract.project_id, "wave", items),
        )
        for index, (name, data) in enumerate(items):
            changed = json.loads(data)
            changed["address_probe"] = index
            mutated = list(items)
            mutated[index] = (name, canonical(changed))
            with self.subTest(name=name):
                self.assertNotEqual(
                    baseline,
                    retarget_bundle_address_sha256(
                        contract.project_id, contract.clip_id, tuple(mutated)
                    ),
                )
        noncanonical = list(items)
        noncanonical[0] = (noncanonical[0][0], noncanonical[0][1] + b"\n")
        with self.assertRaises(MotionRetargetBundleContractError):
            retarget_bundle_address_sha256(
                contract.project_id, contract.clip_id, tuple(noncanonical)
            )
        swapped = list(items)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        with self.assertRaises(MotionRetargetBundleContractError):
            retarget_bundle_address_sha256(
                contract.project_id, contract.clip_id, tuple(swapped)
            )

    def test_hashes_match_canonical_documents_not_object_identity(self):
        contract = self.build()
        documents = contract.document_bytes
        self.assertEqual(
            contract.target_profile_sha256,
            canonical_sha256(json.loads(documents["target-profile.json"])),
        )
        self.assertEqual(
            contract.instance_sha256,
            canonical_sha256(json.loads(documents["instance.json"])),
        )


if __name__ == "__main__":
    unittest.main()
