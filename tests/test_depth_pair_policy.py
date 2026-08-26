"""Reviewed DepthPairPolicy v1 semantic and source-binding tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

from autospine_workbench.depth_order_inputs import (  # noqa: E402
    DepthOrderInputError,
    require_depth_order_inputs,
)
from autospine_workbench.depth_pair_policy import (  # noqa: E402
    DepthPairPolicyError,
    depth_pair_policy_sha256,
    require_depth_pair_policy,
)
from tests.depth_order_helpers import DepthOrderFixture  # noqa: E402


class DepthPairPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = DepthOrderFixture(Path(self.temporary.name))
        self.inputs = require_depth_order_inputs(
            self.fixture.projected, self.fixture.retarget, self.fixture.mesh
        )
        self.policy = self.fixture.policy(self.inputs)

    def test_reviewed_policy_binds_every_stage_identity_and_setup_order(self):
        require_depth_pair_policy(self.policy, inputs=self.inputs)
        self.assertEqual(depth_pair_policy_sha256(self.policy),
                         depth_pair_policy_sha256(deepcopy(self.policy)))
        self.assertEqual(self.inputs.identities, self.policy["source"])
        self.assertEqual("face", self.policy["pairs"][0]["setup_front_slot"])

    def test_missing_slot_wrong_bone_setup_front_and_stale_sha_fail(self):
        cases = []
        missing = deepcopy(self.policy)
        missing["pairs"][0]["slots"][0]["slot_id"] = "absent"
        missing["pairs"][0]["setup_front_slot"] = "absent"
        cases.append((missing, "absent from P3"))
        wrong_role = deepcopy(self.policy)
        wrong_role["pairs"][0]["slots"][0]["depth_role"] = (
            "humanoid.arm.upper.left"
        )
        cases.append((wrong_role, "does not match slot bone"))
        wrong_front = deepcopy(self.policy)
        wrong_front["pairs"][0]["setup_front_slot"] = "leg"
        cases.append((wrong_front, "setup draw order"))
        stale = deepcopy(self.policy)
        stale["source"]["p8"]["bundle_sha256"] = "f" * 64
        cases.append((stale, "source binding is stale"))
        for document, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                DepthPairPolicyError, message
            ):
                require_depth_pair_policy(document, inputs=self.inputs)

    def test_duplicate_or_reversed_pair_and_bad_hysteresis_fail(self):
        duplicate = deepcopy(self.policy)
        repeated = deepcopy(duplicate["pairs"][0])
        repeated["pair_id"] = "face-vs-leg.second"
        duplicate["pairs"].append(repeated)
        with self.assertRaisesRegex(DepthPairPolicyError, "duplicated"):
            require_depth_pair_policy(duplicate)

        reversed_pair = deepcopy(self.policy)
        reversed_pair["pairs"][0]["slots"].reverse()
        with self.assertRaisesRegex(DepthPairPolicyError, "sorted"):
            require_depth_pair_policy(reversed_pair)

        for enter, exit_ in ((0.02, 0.02), (0.01, 0.02), (0.01, -0.01)):
            changed = deepcopy(self.policy)
            changed["hysteresis"].update(
                enter_threshold=enter, exit_threshold=exit_
            )
            with self.subTest(values=(enter, exit_)), self.assertRaisesRegex(
                DepthPairPolicyError, "enter > exit"
            ):
                require_depth_pair_policy(changed)

    def test_collapsed_policy_role_fails_loud(self):
        projected = deepcopy(self.inputs.projected)
        head = next(row for row in projected["segment_tracks"]
                    if row["role"] == "humanoid.head")
        head["samples"][1]["projection_state"] = "collapsed"
        collapsed = replace(self.inputs, projected=projected)
        with self.assertRaisesRegex(DepthPairPolicyError, "collapsed"):
            require_depth_pair_policy(self.policy, inputs=collapsed)

    def test_stale_verified_bundle_shells_fail_exact_admission(self):
        stale_mesh = replace(
            self.fixture.mesh, run_sha256="f" * 64
        )
        with self.assertRaisesRegex(
            DepthOrderInputError, "P3 bundle differs"
        ):
            require_depth_order_inputs(
                self.fixture.projected, self.fixture.retarget, stale_mesh
            )

        sources = self.fixture.retarget.source_addresses
        sources["p3_rig_sha256"] = "f" * 64
        stale_retarget = replace(
            self.fixture.retarget,
            _source_items=tuple(sources.items()),
        )
        with self.assertRaisesRegex(
            DepthOrderInputError, "P5 identities differ"
        ):
            require_depth_order_inputs(
                self.fixture.projected, stale_retarget, self.fixture.mesh
            )

    @unittest.skipIf(Draft202012Validator is None, "install test extra")
    def test_schema_is_valid_and_accepts_policy(self):
        schema = json.loads((
            ROOT / "schemas" / "depth-pair-policy-v1.schema.json"
        ).read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            [], list(Draft202012Validator(schema).iter_errors(self.policy))
        )


if __name__ == "__main__":
    unittest.main()
