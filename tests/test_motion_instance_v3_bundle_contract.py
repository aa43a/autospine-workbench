"""Pure contract and run tests for MotionInstance v3 bundles."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.motion_instance_v3_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
    MotionInstanceV3BundleContractError,
    build_motion_instance_v3_bundle_contract,
    motion_instance_v3_bundle_address_sha256,
)
from autospine_workbench.motion_instance_v3_bundle_run import (  # noqa: E402
    COMPILER,
    MotionInstanceV3BundleRunError,
    require_motion_instance_v3_bundle_run,
)
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    patched_probe_replay,
)
from tests.motion_instance_v3_bundle_helpers import (  # noqa: E402
    MotionInstanceV3StorageFixture,
)


class MotionInstanceV3BundleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = MotionInstanceV3StorageFixture(
            Path(cls.temporary.name)
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def build(self, admission=None, instance=None, project_id=None):
        fixture = self.fixture
        with patched_probe_replay(fixture.probe, fixture.identity):
            return build_motion_instance_v3_bundle_contract(
                project_id or fixture.reviewed_bundle.project_id,
                admission or fixture.admission.document,
                instance or fixture.motion_instance_v3.document,
                fixture.reviewed_bundle,
            )

    def test_deterministic_three_file_contract_and_copy_isolation(self):
        first = self.build()
        second = self.build(
            deepcopy(self.fixture.admission.document),
            deepcopy(self.fixture.motion_instance_v3.document),
        )
        self.assertEqual(DOCUMENT_NAMES, first.inventory)
        self.assertEqual(first.bundle_sha256, second.bundle_sha256)
        self.assertEqual(first.document_bytes, second.document_bytes)
        self.assertEqual(12, len(first.identities))
        isolated = first.document_bytes
        isolated[DOCUMENT_NAMES[0]] = b"changed"
        self.assertNotEqual(isolated, first.document_bytes)

    def test_run_binds_every_required_identity_and_compiler(self):
        contract = self.build()
        run = json.loads(contract.document_bytes["run-manifest.json"])
        source = self.fixture.motion_instance_v3.document["source"]
        self.assertEqual(COMPILER, run["compiler"])
        self.assertEqual(contract.admission_sha256, run["inputs"][
            "body_sway_motion_consumer_admission_sha256"
        ])
        for field in (
            "motion_domain_sha256", "rotation_timeline_sha256",
            "base_channels_sha256", "rig_ir_sha256",
            "target_profile_sha256",
        ):
            self.assertEqual(source[field], run["inputs"][field])
        self.assertEqual(source["p9"], run["inputs"]["p9"])
        self.assertEqual(contract.motion_instance_v3_sha256, run["outputs"][
            "motion_instance_v3_sha256"
        ])
        self.assertEqual(
            contract.motion_instance_v3_profile_sha256,
            run["outputs"]["motion_instance_v3_profile_sha256"],
        )
        self.assertIsNone(require_motion_instance_v3_bundle_run(run))

    def test_admission_v3_project_or_run_shape_tamper_fails_closed(self):
        admission = deepcopy(self.fixture.admission.document)
        admission["claims"]["runtime_equivalence"] = True
        with self.assertRaises(MotionInstanceV3BundleContractError):
            self.build(admission=admission)

        instance = deepcopy(self.fixture.motion_instance_v3.document)
        instance["source"]["motion_domain_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            MotionInstanceV3BundleContractError, "differs from exact"
        ):
            self.build(instance=instance)

        with self.assertRaisesRegex(
            MotionInstanceV3BundleContractError, "project"
        ):
            self.build(project_id="different-project")

        run = json.loads(self.build().document_bytes["run-manifest.json"])
        for mutate in (
            lambda row: row.__setitem__("latest", True),
            lambda row: row["compiler"].__setitem__("version", "latest"),
            lambda row: row["inputs"].__setitem__(
                "motion_domain_sha256", "A" * 64
            ),
        ):
            changed = deepcopy(run)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(
                MotionInstanceV3BundleRunError
            ):
                require_motion_instance_v3_bundle_run(changed)

    def test_address_is_ordered_and_rejects_primary_or_budget_tamper(self):
        contract = self.build()
        items = tuple(contract.document_bytes.items())
        self.assertEqual(contract.bundle_sha256,
                         motion_instance_v3_bundle_address_sha256(
                             contract.project_id,
                             contract.motion_instance_v3_sha256,
                             items,
                         ))
        with self.assertRaisesRegex(
            MotionInstanceV3BundleContractError, "order"
        ):
            motion_instance_v3_bundle_address_sha256(
                contract.project_id,
                contract.motion_instance_v3_sha256,
                (items[1], items[0], items[2]),
            )
        with self.assertRaisesRegex(
            MotionInstanceV3BundleContractError, "differ"
        ):
            motion_instance_v3_bundle_address_sha256(
                contract.project_id, "0" * 64, items
            )
        with patch(
            "autospine_workbench.motion_instance_v3_bundle_contract."
            "MAX_TOTAL_DOCUMENT_BYTES",
            sum(len(data) for _name, data in items) - 1,
        ), self.assertRaisesRegex(
            MotionInstanceV3BundleContractError, "total byte limit"
        ):
            motion_instance_v3_bundle_address_sha256(
                contract.project_id,
                hashlib.sha256(items[1][1]).hexdigest(),
                items,
            )


if __name__ == "__main__":
    unittest.main()
