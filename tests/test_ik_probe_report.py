"""Contract tests for deterministic P4 IK target probe reports."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None

from autospine_workbench.ik_probe_report import (  # noqa: E402
    CASE_ORDER,
    IkProbeReportError,
    build_ik_probe_report,
    probe_config,
    require_ik_probe_report,
)
from autospine_workbench.ik_target_geometry import (  # noqa: E402
    HANDLE_SPECS,
    solver_config,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402


SHA = "1" * 64
SOURCE_FIELDS = (
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256",
    "probes_sha256", "visuals_sha256", "bundle_sha256",
)


def profile_fixture(*, equal_lengths: bool = False) -> dict:
    handles = []
    for index, (handle_id, limb, side, proximal_id, distal_id) in enumerate(HANDLE_SPECS):
        root = (20.0 + index * 30.0, 25.0 + index * 20.0)
        proximal, distal = 5.0, 5.0 if equal_lengths else 4.0
        distal_local = 60.0 if side == "left" else -60.0
        hinge = (root[0] + proximal, root[1])
        angle = math.radians(distal_local)
        effector = (
            hinge[0] + distal * math.cos(angle),
            hinge[1] + distal * math.sin(angle),
        )
        aim = (effector[0] - root[0], effector[1] - root[1])
        aim_length = math.hypot(*aim)
        cross = aim[0] * (hinge[1] - root[1]) - aim[1] * (hinge[0] - root[0])
        handles.append({
            "id": handle_id, "limb": limb, "side": side,
            "proximal_bone_id": proximal_id, "distal_bone_id": distal_id,
            "root_xy": list(root), "hinge_xy": list(hinge),
            "setup_effector_xy": list(effector),
            "proximal_length_px": proximal, "distal_length_px": distal,
            "kinematic_reach": {
                "minimum_px": abs(proximal - distal),
                "maximum_px": proximal + distal,
            },
            "setup_angles_deg": {
                "proximal_world": 0.0, "distal_world": distal_local,
                "proximal_parent_world": 0.0, "proximal_local": 0.0,
                "distal_local": distal_local,
            },
            "bend_direction": "positive" if cross > 0 else "negative",
            "bend_source": "setup.aim_cross_elbow",
            "fallback_direction": {
                "source": "setup.root_to_effector",
                "xy": [aim[0] / aim_length, aim[1] / aim_length],
            },
        })
    return {
        "format": "autospine-ik-target-profile", "format_version": 1,
        "project_id": "sample", "source": {field: SHA for field in SOURCE_FIELDS},
        "canvas": {
            "width": 256, "height": 256, "origin": "top_left",
            "x_axis": "right", "y_axis": "down", "units": "pixel",
        },
        "solver": {
            "id": "autospine-two-bone-analytic", "version": "1.0.0",
            "config": solver_config(),
        },
        "handles": handles,
    }


class IkProbeReportTests(unittest.TestCase):
    def test_four_handles_pass_all_required_cases(self) -> None:
        profile = profile_fixture()
        document = build_ik_probe_report(profile).document

        self.assertEqual("passed", document["status"])
        self.assertEqual({
            "handle_count": 4,
            "evaluated_case_count": 20,
            "not_applicable_case_count": 0,
        }, document["summary"])
        self.assertEqual(
            canonical_sha256(profile), document["source"]["profile_sha256"]
        )
        self.assertEqual(probe_config(), document["prober"]["config"])
        for entry, source_handle in zip(document["handles"], profile["handles"]):
            self.assertEqual(list(CASE_ORDER), [case["id"] for case in entry["cases"]])
            self.assertEqual("passed", entry["gate"]["status"])
            self.assertEqual("not_evaluated", entry["mesh_visual_safety"]["status"])
            cases = {case["id"]: case for case in entry["cases"]}
            self.assertEqual("reachable", cases["setup"]["reach_state"])
            self.assertEqual("reachable", cases["reachable-mid"]["reach_state"])
            self.assertEqual("unreachable_too_far", cases["unreachable-far"]["reach_state"])
            self.assertEqual("unreachable_too_near", cases["unreachable-near"]["reach_state"])
            self.assertEqual("unreachable_too_near", cases["coincident-target"]["reach_state"])
            self.assertTrue(cases["coincident-target"]["used_fallback_direction"])
            setup = cases["setup"]
            self.assert_point(source_handle["hinge_xy"], setup["hinge_xy"])
            self.assert_point(source_handle["setup_effector_xy"], setup["effector_xy"])
            self.assertAlmostEqual(0.0, setup["setup_local_deltas_deg"]["proximal"])
            self.assertAlmostEqual(0.0, setup["setup_local_deltas_deg"]["distal"])
            for case in entry["cases"]:
                self.assertEqual("passed", case["status"])
                for value in case["metrics"].values():
                    if value is not None:
                        self.assertTrue(math.isfinite(value))
        require_ik_probe_report(document, profile=profile)

    def test_zero_minimum_reach_marks_near_case_not_applicable(self) -> None:
        profile = profile_fixture(equal_lengths=True)
        document = build_ik_probe_report(profile).document

        self.assertEqual(16, document["summary"]["evaluated_case_count"])
        self.assertEqual(4, document["summary"]["not_applicable_case_count"])
        for entry in document["handles"]:
            near = entry["cases"][3]
            self.assertEqual({
                "id": "unreachable-near",
                "applicability": "not_applicable",
                "reason": "minimum_kinematic_reach_is_zero",
                "status": "not_applicable",
            }, near)
            coincident = entry["cases"][4]
            self.assertEqual("reachable", coincident["reach_state"])
            self.assertTrue(coincident["used_fallback_direction"])
        require_ik_probe_report(document, profile=profile)

    def test_report_is_deterministic_isolated_and_does_not_mutate_profile(self) -> None:
        profile = profile_fixture()
        before = deepcopy(profile)
        first = build_ik_probe_report(profile)
        second = build_ik_probe_report(dict(reversed(list(profile.items()))))

        self.assertEqual(before, profile)
        self.assertEqual(first.to_json(), second.to_json())
        changed = first.document
        changed["handles"][0]["cases"].clear()
        self.assertEqual(5, len(first.document["handles"][0]["cases"]))

    def test_rebuild_rejects_identity_config_case_and_numeric_drift(self) -> None:
        profile = profile_fixture()
        original = build_ik_probe_report(profile).document
        mutations = (
            lambda value: value["source"].update(profile_sha256="2" * 64),
            lambda value: value["prober"]["config"].update(far_radius_multiplier=2),
            lambda value: value["handles"][0]["cases"].reverse(),
            lambda value: value["handles"][0]["cases"][0]["metrics"].update(
                proximal_length_error_px=0.1
            ),
            lambda value: value.update(unexpected=True),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = deepcopy(original)
                mutate(changed)
                with self.assertRaises(IkProbeReportError):
                    require_ik_probe_report(changed, profile=profile)

        nonfinite = deepcopy(original)
        nonfinite["handles"][0]["cases"][0]["hinge_xy"][0] = math.nan
        with self.assertRaises(IkProbeReportError):
            require_ik_probe_report(nonfinite, profile=profile)

    def test_invalid_profile_fails_before_probing(self) -> None:
        cases = []
        unknown = profile_fixture()
        unknown["handles"][0]["extra"] = True
        cases.append(unknown)
        nonfinite = profile_fixture()
        nonfinite["handles"][0]["root_xy"][0] = math.inf
        cases.append(nonfinite)
        bad_reach = profile_fixture()
        bad_reach["handles"][0]["kinematic_reach"]["maximum_px"] = 99
        cases.append(bad_reach)
        for profile in cases:
            with self.subTest(profile=profile), self.assertRaises(IkProbeReportError):
                build_ik_probe_report(profile)

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_schema_accepts_exact_report_and_rejects_unknown_or_missing_fields(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "ik-target-probes-v1.schema.json").read_text("utf-8")
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        exact = build_ik_probe_report(profile_fixture()).document
        self.assertEqual([], list(validator.iter_errors(exact)))

        changed = deepcopy(exact)
        changed["handles"][0]["cases"][0]["unexpected"] = True
        self.assertTrue(list(validator.iter_errors(changed)))
        missing = deepcopy(exact)
        del missing["handles"][0]["cases"][0]["reach_state"]
        self.assertTrue(list(validator.iter_errors(missing)))

        exact_zero = build_ik_probe_report(profile_fixture(equal_lengths=True)).document
        self.assertEqual([], list(validator.iter_errors(exact_zero)))

    def assert_point(self, expected, actual) -> None:
        self.assertAlmostEqual(expected[0], actual[0], places=8)
        self.assertAlmostEqual(expected[1], actual[1], places=8)


if __name__ == "__main__":
    unittest.main()
