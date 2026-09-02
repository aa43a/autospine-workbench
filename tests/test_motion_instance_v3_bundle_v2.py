"""P10.6b v2 bundle contract, store, and exact-reader tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.motion_instance_v3_bundle_contract_v2 import (  # noqa: E402
    DOCUMENT_NAMES,
    MotionInstanceV3BundleContractV2Error,
    build_motion_instance_v3_bundle_contract_v2,
)
from autospine_workbench.motion_instance_v3_bundle_fs_v2 import (  # noqa: E402
    NAMESPACE,
)
from autospine_workbench.motion_instance_v3_bundle_reader_v2 import (  # noqa: E402
    MotionInstanceV3BundleReaderV2,
    MotionInstanceV3BundleReaderV2Error,
)
from autospine_workbench.motion_instance_v3_bundle_run_v2 import (  # noqa: E402
    AUTHORITY,
    COMPILER,
    RELEASE_GATE,
    MotionInstanceV3BundleRunV2Error,
    require_motion_instance_v3_bundle_run_v2,
)
from autospine_workbench.motion_instance_v3_bundle_store_v2 import (  # noqa: E402
    MotionInstanceV3BundleStoreV2,
    MotionInstanceV3BundleStoreV2Error,
)
from autospine_workbench.seam_anchor_review_json import (  # noqa: E402
    canonical_json_bytes,
)
from tests.motion_instance_v3_bundle_v2_helpers import (  # noqa: E402
    MotionInstanceV3BundleV2Fixture,
)


READER = "autospine_workbench.motion_instance_v3_bundle_reader_v2."


class MotionInstanceV3BundleV2Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = MotionInstanceV3BundleV2Fixture(
            Path(temporary.name),
        )
        self.reader = MotionInstanceV3BundleReaderV2(
            self.fixture.state_root,
        )

    def test_contract_inventory_domain_and_run_are_version_isolated(self):
        contract = self.fixture.contract
        self.assertEqual(DOCUMENT_NAMES, contract.inventory)
        self.assertEqual((
            "body-sway-motion-consumer-admission-v2.json",
            "motion-instance-v3.json", "run-manifest-v2.json",
        ), contract.inventory)
        run = json.loads(contract.document_bytes[DOCUMENT_NAMES[2]])
        self.assertEqual(2, run["format_version"])
        self.assertEqual(COMPILER, run["compiler"])
        self.assertEqual(AUTHORITY, run["authority"])
        self.assertEqual(RELEASE_GATE, run["release_gate"])
        self.assertFalse(run["authority"]["attachment_area_overlap_assessed"])
        self.assertFalse(run["authority"]["dynamic_seam_safety"])
        self.assertFalse(run["authority"][
            "full_attachment_boundary_continuity"
        ])
        self.assertFalse(run["authority"]["publishable_timeline"])
        self.assertEqual({
            "source_set_sha256": self.fixture.dynamic.source_set_sha256,
            "source_document_sha256":
                self.fixture.dynamic.source_document_sha256,
            "probe_sha256": self.fixture.dynamic.probe_sha256,
            "bundle_sha256": self.fixture.dynamic.bundle_sha256,
        }, run["inputs"]["body_sway_dynamic_seam_v2"])
        self.assertIsNone(require_motion_instance_v3_bundle_run_v2(run))

    def test_contract_is_deterministic_and_rejects_v3_or_upstream_crosswire(self):
        first = self.fixture.contract
        second = build_motion_instance_v3_bundle_contract_v2(
            self.fixture.prepared, deepcopy(self.fixture.motion.document),
            self.fixture.dynamic, self.fixture.reviewed,
        )
        self.assertEqual(first.bundle_sha256, second.bundle_sha256)
        self.assertEqual(first.document_bytes, second.document_bytes)
        attack = self.fixture.motion.document
        attack["source"]["rig_ir_sha256"] = "0" * 64
        with self.assertRaises(MotionInstanceV3BundleContractV2Error):
            build_motion_instance_v3_bundle_contract_v2(
                self.fixture.prepared, attack,
                self.fixture.dynamic, self.fixture.reviewed,
            )

    def test_run_rejects_v1_extra_and_authority_overclaims(self):
        run = json.loads(
            self.fixture.contract.document_bytes[DOCUMENT_NAMES[2]],
        )
        attacks = []
        v1 = deepcopy(run)
        v1["format_version"] = 1
        attacks.append(v1)
        extra = deepcopy(run)
        extra["latest"] = True
        attacks.append(extra)
        overlap = deepcopy(run)
        overlap["authority"]["attachment_area_overlap_assessed"] = True
        attacks.append(overlap)
        release = deepcopy(run)
        release["release_gate"]["status"] = "passed"
        attacks.append(release)
        source = deepcopy(run)
        source["inputs"]["body_sway_dynamic_seam_v2"].pop(
            "source_document_sha256"
        )
        attacks.append(source)
        for index, attack in enumerate(attacks):
            with self.subTest(index=index), self.assertRaises(
                MotionInstanceV3BundleRunV2Error,
            ):
                require_motion_instance_v3_bundle_run_v2(attack)

    def test_atomic_publish_is_idempotent_and_never_writes_latest(self):
        first = self.fixture.publish()
        second = self.fixture.publish()
        contract = self.fixture.contract
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual((
            contract.bundle_sha256,
            contract.motion_instance_v3_sha256,
            NAMESPACE, contract.project_id, "builds",
        ), (
            first.path.name, first.path.parent.name,
            first.path.parent.parent.name,
            first.path.parent.parent.parent.name,
            first.path.parent.parent.parent.parent.name,
        ))
        self.assertFalse((first.path.parent / "latest").exists())

    def test_stale_or_drifting_current_heads_fail_before_write(self):
        store = MotionInstanceV3BundleStoreV2(
            self.fixture.capture, self.fixture.project_store,
        )
        target = (
            self.fixture.state_root / "builds"
            / self.fixture.contract.project_id / NAMESPACE
        )
        with patch(
            "autospine_workbench.motion_instance_v3_bundle_store_v2."
            "require_current_body_sway_dynamic_seam_heads_v2",
            side_effect=RuntimeError("stale"),
        ), self.assertRaises(MotionInstanceV3BundleStoreV2Error):
            self._publish(store)
        self.assertFalse(target.exists())

        observed = self.fixture.observation
        drift = SimpleNamespace(
            identity_sha256=observed.identity_sha256,
            canonical_bytes=observed.canonical_bytes + b"drift",
        )
        with self.fixture.publish_gate(
            observations=(observed, drift),
        ), self.assertRaises(MotionInstanceV3BundleStoreV2Error):
            self._publish(store)
        self.assertFalse(target.exists())

    def test_historical_reader_loads_dynamic_once_and_never_checks_heads(self):
        self.fixture.publish()
        contract = self.fixture.contract
        import autospine_workbench.body_sway_dynamic_seam_bundle_reader_v2 \
            as dynamic_reader_module

        with self.fixture.historical_replay(), patch(
            READER + "BodySwayDynamicSeamBundleReaderV2.load",
            wraps=dynamic_reader_module.BodySwayDynamicSeamBundleReaderV2(
                self.fixture.state_root,
            ).load,
        ) as dynamic_load, patch(
            READER + "VerifiedReviewedMotionBundleReader.load",
            return_value=self.fixture.reviewed,
        ) as reviewed_load, patch(
            "autospine_workbench.body_sway_dynamic_seam_head_checks_v2."
            "require_current_body_sway_dynamic_seam_heads_v2",
            side_effect=AssertionError("current heads observed"),
        ):
            verified = self.reader.load(
                contract.project_id, contract.motion_instance_v3_sha256,
                contract.bundle_sha256,
            )
        self.assertEqual(1, dynamic_load.call_count)
        self.assertEqual(1, reviewed_load.call_count)
        self.assertEqual(contract.identities, verified.identities)
        self.assertEqual(contract.document_bytes, verified.document_bytes)

    def test_compile_readback_reuses_prepared_and_verified_upstreams(self):
        self.fixture.publish()
        contract = self.fixture.contract
        with patch(
            READER + "BodySwayDynamicSeamBundleReaderV2.load",
            side_effect=AssertionError("dynamic reloaded"),
        ), patch(
            READER + "replay_motion_instance_v3_prepared_v2",
            side_effect=AssertionError("prepared replayed"),
        ):
            verified = self.reader.load(
                contract.project_id, contract.motion_instance_v3_sha256,
                contract.bundle_sha256,
                dynamic_bundle=self.fixture.dynamic,
                reviewed_bundle=self.fixture.reviewed,
                prepared=self.fixture.prepared,
            )
        self.assertEqual(contract.bundle_sha256, verified.bundle_sha256)

    def test_reader_issued_value_cannot_be_replaced(self):
        self.fixture.publish()
        contract = self.fixture.contract
        verified = self.reader.load(
            contract.project_id, contract.motion_instance_v3_sha256,
            contract.bundle_sha256, dynamic_bundle=self.fixture.dynamic,
            reviewed_bundle=self.fixture.reviewed,
            prepared=self.fixture.prepared,
        )
        with self.assertRaises(MotionInstanceV3BundleReaderV2Error):
            replace(verified, bundle_sha256="0" * 64)

    def test_wrong_explicit_address_and_traversal_never_fall_back(self):
        self.fixture.publish()
        contract = self.fixture.contract
        for project, primary, bundle in (
            ("../escape", contract.motion_instance_v3_sha256,
             contract.bundle_sha256),
            (contract.project_id, "0" * 64, contract.bundle_sha256),
            (contract.project_id, contract.motion_instance_v3_sha256,
             "0" * 64),
        ):
            with self.subTest(project=project, primary=primary), \
                    self.assertRaises(MotionInstanceV3BundleReaderV2Error):
                self.reader.load(
                    project, primary, bundle,
                    dynamic_bundle=self.fixture.dynamic,
                    reviewed_bundle=self.fixture.reviewed,
                    prepared=self.fixture.prepared,
                )
        self.assertFalse((self.fixture.root / "escape").exists())

    def test_document_tamper_and_extra_inventory_fail_closed(self):
        published = self.fixture.publish()
        contract = self.fixture.contract
        for name in DOCUMENT_NAMES:
            path = published.path / name
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            try:
                with self.subTest(name=name), self.assertRaises(
                    MotionInstanceV3BundleReaderV2Error,
                ):
                    self.reader.load(
                        contract.project_id,
                        contract.motion_instance_v3_sha256,
                        contract.bundle_sha256,
                        dynamic_bundle=self.fixture.dynamic,
                        reviewed_bundle=self.fixture.reviewed,
                        prepared=self.fixture.prepared,
                    )
            finally:
                path.write_bytes(original)
        extra = published.path / "latest.json"
        extra.write_bytes(b"{}")
        with self.assertRaises(MotionInstanceV3BundleReaderV2Error):
            self.reader.load(
                contract.project_id, contract.motion_instance_v3_sha256,
                contract.bundle_sha256,
                dynamic_bundle=self.fixture.dynamic,
                reviewed_bundle=self.fixture.reviewed,
                prepared=self.fixture.prepared,
            )

    def _publish(self, store):
        return store.publish(
            self.fixture.prepared, self.fixture.motion.document,
            self.fixture.dynamic, self.fixture.reviewed,
        )


if __name__ == "__main__":
    unittest.main()
