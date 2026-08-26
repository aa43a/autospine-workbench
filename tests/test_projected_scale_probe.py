"""P8 target-rig foreshortening candidate probe acceptance tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
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

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None

from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from autospine_workbench.projected_motion_bundle_reader import (  # noqa: E402
    VerifiedProjectedMotionBundleReader,
)
from autospine_workbench.projected_scale_probe import (  # noqa: E402
    ProjectedScaleProbeError,
    compile_projected_scale_probes,
)
from autospine_workbench.projected_scale_probe_validation import (  # noqa: E402
    ProjectedScaleProbeValidationError,
    require_projected_scale_probes,
)
from tests.projected_motion_bundle_helpers import (  # noqa: E402
    ProjectedBundleFixture,
)
from tests.test_motion_target_profile import pair  # noqa: E402
from tests.test_motion_three_rig_gate import (  # noqa: E402
    ASYMMETRIC_SETUP,
    rig_from_setup,
    tall_asymmetric_rig,
)


def _rotate_y(degrees: float) -> tuple[tuple[float, ...], ...]:
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    return (
        (cosine, 0.0, sine),
        (0.0, 1.0, 0.0),
        (-sine, 0.0, cosine),
    )


def _track(document: dict, role: str) -> dict:
    return next(row for row in document["tracks"] if row["role"] == role)


def _json_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _json_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_keys(child)


class ProjectedScaleProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        fixture = ProjectedBundleFixture(
            Path(cls.temporary.name),
            motion_kwargs={
                "local_overrides": {(1, "LeftArm"): _rotate_y(60.0)},
            },
        )
        published = fixture.publish()
        cls.bundle = VerifiedProjectedMotionBundleReader(fixture.state).load(
            published.projected_motion_sha256,
            published.bundle_sha256,
        )
        cls.profiles = [
            compile_motion_target_profile(*pair()),
            compile_motion_target_profile(*pair(
                rig=rig_from_setup(ASYMMETRIC_SETUP)
            )),
            compile_motion_target_profile(*pair(rig=tall_asymmetric_rig())),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_ratio_math_is_setup_relative_and_deterministic(self):
        profile = self.profiles[0]
        first = compile_projected_scale_probes(self.bundle, profile.document)
        second = compile_projected_scale_probes(self.bundle, profile.document)
        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.document, json.loads(first.canonical_json))

        upper = _track(first.document, "humanoid.arm.upper.left")
        self.assertEqual(35.0, upper["setup_length_px"])
        self.assertEqual(1.0, upper["setup_foreshortening_ratio"])
        for actual, expected in zip(
            [sample["scale_x_candidate"] for sample in upper["samples"]],
            [1.0, 0.5, 1.0],
        ):
            self.assertAlmostEqual(expected, actual, places=7)
        for actual, expected in zip(
            [sample["candidate_length_px"] for sample in upper["samples"]],
            [35.0, 17.5, 35.0],
        ):
            self.assertAlmostEqual(expected, actual, places=6)
        for actual, expected in zip(
            [sample["delta_length_px"] for sample in upper["samples"]],
            [0.0, -17.5, 0.0],
        ):
            self.assertAlmostEqual(expected, actual, places=6)
        self.assertEqual(
            [sample["tick"] for sample in upper["samples"]],
            [0, 33333, 66667],
        )

    def test_source_and_target_are_exactly_bound(self):
        profile = self.profiles[0]
        report = compile_projected_scale_probes(
            self.bundle, profile.document
        ).document
        source = report["source"]
        self.assertEqual(self.bundle.projected_motion_sha256,
                         source["projected_motion_sha256"])
        self.assertEqual(self.bundle.bundle_sha256,
                         source["projected_bundle_sha256"])
        self.assertEqual(self.bundle.camera_sha256, source["camera_sha256"])
        self.assertEqual(self.bundle.p7_motion_sha256,
                         source["p7_motion_sha256"])
        self.assertEqual(profile.sha256, source["target_profile_sha256"])
        p3 = profile.document["source"]["p3"]
        self.assertEqual(p3["rig_sha256"], source["p3_rig_sha256"])
        self.assertEqual(p3["bundle_sha256"], source["p3_bundle_sha256"])
        require_projected_scale_probes(
            report,
            projected_bundle=self.bundle,
            target_profile=profile.document,
        )

        wrong_p8 = deepcopy(report)
        wrong_p8["source"]["projected_bundle_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            ProjectedScaleProbeValidationError, "P8 source binding"
        ):
            require_projected_scale_probes(
                wrong_p8, projected_bundle=self.bundle
            )
        wrong_target = deepcopy(report)
        wrong_target["source"]["target_profile_sha256"] = "e" * 64
        with self.assertRaisesRegex(
            ProjectedScaleProbeValidationError, "target binding"
        ):
            require_projected_scale_probes(
                wrong_target, target_profile=profile.document
            )

    def test_malformed_math_collapsed_evidence_and_inputs_fail_closed(self):
        profile = self.profiles[0]
        report = compile_projected_scale_probes(
            self.bundle, profile.document
        ).document
        wrong_math = deepcopy(report)
        wrong_math["tracks"][0]["samples"][1]["scale_x_candidate"] += 0.25
        with self.assertRaisesRegex(
            ProjectedScaleProbeValidationError, "math is inconsistent"
        ):
            require_projected_scale_probes(wrong_math)

        wrong_ticks = deepcopy(report)
        wrong_ticks["tracks"][1]["samples"][1]["tick"] += 1
        with self.assertRaisesRegex(
            ProjectedScaleProbeValidationError, "ticks must be shared"
        ):
            require_projected_scale_probes(wrong_ticks)

        projected = self.bundle.projected_motion
        sample = projected["segment_tracks"][0]["samples"][1]
        source_length = sample["source_length_normalized"]
        start_depth = sample["start_depth_root_relative_normalized"]
        sample.update(
            projected_vector_normalized=[0.0, 0.0],
            projected_length_normalized=0.0,
            foreshortening_ratio=0.0,
            depth_cosine=1.0,
            end_depth_root_relative_normalized=start_depth + source_length,
            midpoint_depth_root_relative_normalized=(
                start_depth + source_length / 2.0
            ),
            projection_state="collapsed",
        )
        encoded = json.dumps(
            projected, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        malformed_bundle = replace(
            self.bundle,
            _documents=tuple(
                (name, encoded if name == "projected-motion.json" else payload)
                for name, payload in self.bundle._documents
            ),
        )
        with self.assertRaisesRegex(ProjectedScaleProbeError, "collapsed"):
            compile_projected_scale_probes(
                malformed_bundle, profile.document
            )
        with self.assertRaisesRegex(ProjectedScaleProbeError, "verified P8"):
            compile_projected_scale_probes(object(), profile.document)
        invalid_target = profile.document
        invalid_target["target_space"]["scale"] = "arbitrary"
        with self.assertRaises(ProjectedScaleProbeError):
            compile_projected_scale_probes(self.bundle, invalid_target)

    def test_report_is_candidate_only_and_does_not_mutate_inputs(self):
        profile = self.profiles[0]
        before_target = deepcopy(profile.document)
        before_projected = deepcopy(self.bundle.projected_motion)
        compiled = compile_projected_scale_probes(
            self.bundle, profile.document
        )
        document = compiled.document
        self.assertEqual(before_target, profile.document)
        self.assertEqual(before_projected, self.bundle.projected_motion)
        self.assertEqual("positive-unit-only",
                         profile.document["target_space"]["scale"])
        self.assertEqual({
            "mode": "candidate_only",
            "formula": "foreshortening_ratio_over_setup_ratio",
            "application": "independent_target_bone_length_probe",
            "baseline": "source_frame0",
            "target_scale_contract": "positive-unit-only-unchanged",
            "runtime_timeline_emitted": False,
            "depth_consumption": "none",
            "collapsed_policy": "reject_report",
        }, document["policy"])
        self.assertTrue({"animations", "animation", "timelines", "timeline"}
                        .isdisjoint(_json_keys(document)))

        isolated = compiled.document
        isolated["tracks"].clear()
        self.assertEqual(
            len(self.bundle.projected_motion["segment_tracks"]),
            len(compiled.document["tracks"]),
        )

    def test_same_projection_evidence_is_reused_across_three_target_rigs(self):
        reports = [
            compile_projected_scale_probes(self.bundle, profile.document)
            for profile in self.profiles
        ]
        self.assertEqual(3, len({profile.sha256 for profile in self.profiles}))
        self.assertEqual(3, len({report.sha256 for report in reports}))
        self.assertEqual({self.bundle.projected_motion_sha256}, {
            report.document["source"]["projected_motion_sha256"]
            for report in reports
        })
        self.assertEqual({self.bundle.bundle_sha256}, {
            report.document["source"]["projected_bundle_sha256"]
            for report in reports
        })
        tracks = [
            _track(report.document, "humanoid.arm.upper.left")
            for report in reports
        ]
        self.assertEqual(1, len({tuple(
            sample["scale_x_candidate"] for sample in track["samples"]
        ) for track in tracks}))
        self.assertEqual([35.0, 51.0, 58.0], [
            track["setup_length_px"] for track in tracks
        ])
        for actual, expected in zip(
            [track["samples"][1]["candidate_length_px"] for track in tracks],
            [17.5, 25.5, 29.0],
        ):
            self.assertAlmostEqual(expected, actual, places=6)
        for report, profile in zip(reports, self.profiles):
            require_projected_scale_probes(
                report.document,
                projected_bundle=self.bundle,
                target_profile=profile.document,
            )

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_schema_is_valid_and_accepts_exact_report(self):
        schema = json.loads((
            ROOT / "schemas" / "projected-scale-probes-v1.schema.json"
        ).read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        report = compile_projected_scale_probes(
            self.bundle, self.profiles[0].document
        ).document
        self.assertEqual(
            [], list(Draft202012Validator(schema).iter_errors(report))
        )


if __name__ == "__main__":
    unittest.main()
