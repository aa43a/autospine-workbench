"""P10.2 exact in-memory admission tests for reviewed body-sway probes."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.body_sway_probe_inputs import (
    BodySwayProbeInputError,
    require_body_sway_probe_inputs,
)
from autospine_workbench.idle_behavior_candidates import (
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_candidate_validation import (
    idle_behavior_candidates_sha256,
)
from autospine_workbench.idle_behavior_decision import (
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_decision_validation import (
    idle_behavior_decision_sha256,
)
from tests.idle_behavior_decision_helpers import (
    adjust_decision,
    completed_review,
    terminal_decision,
)
from tests.idle_behavior_helpers import IdleBehaviorFixture


class _BundleProxy:
    """Attribute-compatible object that must not cross an exact-type boundary."""

    def __init__(self, value) -> None:
        self._value = value

    def __getattr__(self, name):
        return getattr(self._value, name)


class BodySwayProbeInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = IdleBehaviorFixture(Path(cls.temporary.name))
        cls.candidates = compile_idle_behavior_candidates(
            cls.fixture.manifest, cls.fixture.mesh,
            cls.fixture.retarget, cls.fixture.reviewed,
        ).document
        cls.decision = build_idle_behavior_decision(
            cls.candidates,
            review=completed_review(),
            decisions=[adjust_decision(cls.candidates)],
        ).document

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def admit(self, **changes):
        fixture = self.fixture
        values = {
            "layer_manifest": fixture.manifest,
            "candidates": self.candidates,
            "decision": self.decision,
            "mesh_bundle": fixture.mesh,
            "retarget_bundle": fixture.retarget,
            "reviewed_bundle": fixture.reviewed,
        }
        values.update(changes)
        return require_body_sway_probe_inputs(**values)

    def test_exact_chain_returns_complete_detached_inventory(self):
        admitted = self.admit()
        expected_upstream = self.candidates["source"]
        self.assertEqual(self.candidates["project_id"], admitted.project_id)
        self.assertEqual(self.candidates["clip_id"], admitted.clip_id)
        self.assertEqual(self.candidates["timing"], admitted.timing)
        self.assertEqual(self.fixture.mesh.rig, admitted.rig)
        self.assertEqual(self.fixture.retarget.target_profile,
                         admitted.target_profile)
        self.assertEqual(self.candidates, admitted.candidates)
        self.assertEqual(self.decision, admitted.decision)
        decision_row = self.decision["decisions"][0]
        self.assertEqual({
            "candidate_id": decision_row["candidate_id"],
            "feature_id": "body_sway",
            "action": "adjust",
            "probe_status": "pending_probe",
            "parameters": decision_row["payload"],
        }, admitted.selection)
        self.assertEqual(expected_upstream, {
            key: admitted.source[key]
            for key in ("layer_manifest_sha256", "p3", "p5", "p9")
        })
        self.assertEqual(
            idle_behavior_candidates_sha256(self.candidates),
            admitted.source["idle_behavior_candidates_sha256"],
        )
        self.assertEqual(
            idle_behavior_decision_sha256(self.decision),
            admitted.source["idle_behavior_decision_sha256"],
        )

    def test_value_is_deterministic_frozen_non_mutating_and_detached(self):
        before = deepcopy((
            self.fixture.manifest, self.candidates, self.decision,
        ))
        first, second = self.admit(), self.admit()
        self.assertEqual(first, second)
        self.assertEqual(before, (
            self.fixture.manifest, self.candidates, self.decision,
        ))
        first.source["p3"].clear()
        first.rig["bones"].clear()
        first.selection["parameters"].clear()
        self.assertTrue(first.source["p3"])
        self.assertTrue(first.rig["bones"])
        self.assertTrue(first.selection["parameters"])
        with self.assertRaises(FrozenInstanceError):
            first.project_id = "other"  # type: ignore[misc]

    def test_human_parameter_change_changes_only_decision_identity(self):
        changed_row = adjust_decision(self.candidates)
        changed_row["payload"]["per_bone_amplitude_deg"][0]["value"] = 3.0
        changed = build_idle_behavior_decision(
            self.candidates,
            review=completed_review(2),
            decisions=[changed_row],
        ).document
        baseline, revised = self.admit(), self.admit(decision=changed)
        self.assertEqual(
            baseline.source["idle_behavior_candidates_sha256"],
            revised.source["idle_behavior_candidates_sha256"],
        )
        self.assertNotEqual(
            baseline.source["idle_behavior_decision_sha256"],
            revised.source["idle_behavior_decision_sha256"],
        )
        self.assertNotEqual(baseline.selection, revised.selection)

    def test_candidates_must_match_recompiled_document_and_bytes(self):
        stale = deepcopy(self.candidates)
        stale["project_id"] = "cross-wired-project"
        with self.assertRaisesRegex(BodySwayProbeInputError, "exact P3/P5/P9"):
            self.admit(candidates=stale)

        exact = compile_idle_behavior_candidates(
            self.fixture.manifest, self.fixture.mesh,
            self.fixture.retarget, self.fixture.reviewed,
        )
        mismatched_bytes = SimpleNamespace(
            document=exact.document,
            canonical_bytes=exact.canonical_bytes + b" ",
            sha256=exact.sha256,
        )
        with patch(
            "autospine_workbench.body_sway_probe_inputs."
            "compile_idle_behavior_candidates",
            return_value=mismatched_bytes,
        ), self.assertRaisesRegex(BodySwayProbeInputError, "exact P3/P5/P9"):
            self.admit()

    def test_decision_must_be_candidate_aware_and_not_stale(self):
        mutations = (
            lambda row: row["source"].__setitem__(
                "idle_behavior_candidates_sha256", "0" * 64
            ),
            lambda row: row["decisions"][0].__setitem__(
                "candidate_id", "body-sway-" + "0" * 64
            ),
            lambda row: row.__setitem__("project_id", "cross-wired-project"),
            lambda row: row["timing"].__setitem__("loop", True),
        )
        for mutate in mutations:
            changed = deepcopy(self.decision)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(
                BodySwayProbeInputError
            ):
                self.admit(decision=changed)

    def test_only_one_adjusted_pending_probe_selection_is_admitted(self):
        for action in ("reject", "unobservable"):
            terminal = build_idle_behavior_decision(
                self.candidates,
                review=completed_review(),
                decisions=[terminal_decision(action, self.candidates)],
            ).document
            with self.subTest(action=action), self.assertRaisesRegex(
                BodySwayProbeInputError, "adjusted pending_probe"
            ):
                self.admit(decision=terminal)

        for rows in ([], [deepcopy(self.decision["decisions"][0])] * 2):
            changed = deepcopy(self.decision)
            changed["decisions"] = deepcopy(rows)
            with self.subTest(count=len(rows)), self.assertRaises(
                BodySwayProbeInputError
            ):
                self.admit(decision=changed)

    def test_stale_cross_wired_and_spoofed_exact_bundles_fail_closed(self):
        stale_cases = (
            {"mesh_bundle": replace(
                self.fixture.mesh, bundle_sha256="0" * 64
            )},
            {"retarget_bundle": replace(
                self.fixture.retarget, project_id="cross-wired-project"
            )},
            {"reviewed_bundle": replace(
                self.fixture.reviewed, clip_id="cross-wired-clip"
            )},
        )
        for values in stale_cases:
            with self.subTest(values=tuple(values)), self.assertRaises(
                BodySwayProbeInputError
            ):
                self.admit(**values)

        spoofed_cases = (
            {"mesh_bundle": _BundleProxy(self.fixture.mesh)},
            {"retarget_bundle": _BundleProxy(self.fixture.retarget)},
            {"reviewed_bundle": _BundleProxy(self.fixture.reviewed)},
        )
        for values in spoofed_cases:
            with self.subTest(values=tuple(values)), self.assertRaisesRegex(
                BodySwayProbeInputError, "exact"
            ):
                self.admit(**values)

    def test_manifest_staleness_and_non_object_documents_fail_closed(self):
        manifest = deepcopy(self.fixture.manifest)
        manifest["revision"] += 1
        for values in (
            {"layer_manifest": manifest},
            {"candidates": []},
            {"decision": []},
        ):
            with self.subTest(values=tuple(values)), self.assertRaises(
                BodySwayProbeInputError
            ):
                self.admit(**values)


if __name__ == "__main__":
    unittest.main()
