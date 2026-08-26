"""P8 gate: projection evidence remains optional across three P5/P6 rigs."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_validation import motion_ir_sha256  # noqa: E402
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.projected_motion_bundle_reader import (  # noqa: E402
    VerifiedProjectedMotionBundleReader,
)
from autospine_workbench.projected_scale_probe import (  # noqa: E402
    compile_projected_scale_probes,
)
from autospine_workbench.spine42_atlas import build_spine42_atlas  # noqa: E402
from tests.p5_p6_pipeline_helpers import run_p5_p6_rig  # noqa: E402
from tests.projected_motion_bundle_helpers import ProjectedBundleFixture  # noqa: E402
from tests.test_motion_three_rig_gate import (  # noqa: E402
    ASYMMETRIC_SETUP,
    rig_from_setup,
    tall_asymmetric_rig,
)


def _scale_vector(report: dict) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(
        sample["scale_x_candidate"] for sample in track["samples"]
    ) for track in report["tracks"])


class ProjectedMotionPipelineGateTests(unittest.TestCase):
    def test_projection_and_scale_candidates_do_not_change_p5_or_p6(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ProjectedBundleFixture(Path(temporary))
            published = fixture.publish()
            projected = VerifiedProjectedMotionBundleReader(fixture.state).load(
                published.projected_motion_sha256, published.bundle_sha256
            )

            self.assertEqual(fixture.p7.motion, projected.legacy_motion)
            self.assertEqual(
                fixture.p7.clip_sha256,
                motion_ir_sha256(projected.legacy_motion),
            )
            self.assertEqual(fixture.p7.bundle_sha256, projected.p7_bundle_sha256)

            image = encode_rgba_png(RgbaImage(
                20, 30, bytes((40, 80, 120, 255)) * (20 * 30)
            ))
            atlas = build_spine42_atlas(
                {"face-image": image}, page_name="skeleton.png"
            )
            rigs = (
                rig_from_setup(ASYMMETRIC_SETUP),
                rig_from_setup(ASYMMETRIC_SETUP, x_offset=37),
                tall_asymmetric_rig(),
            )
            reports, results = [], []
            for index, rig in enumerate(rigs):
                with self.subTest(rig=index):
                    result = run_p5_p6_rig(
                        fixture.state, fixture.p7, rig, image, atlas
                    )
                    target_before = deepcopy(result.target.document)
                    probe = compile_projected_scale_probes(
                        projected, result.target.document
                    )
                    report = probe.document
                    self.assertEqual(target_before, result.target.document)
                    self.assertEqual(
                        "positive-unit-only",
                        result.target.document["target_space"]["scale"],
                    )
                    self.assertFalse(
                        report["policy"]["runtime_timeline_emitted"]
                    )
                    self.assertEqual(
                        fixture.p7.bundle_sha256,
                        result.retargeted.instance["source"][
                            "motion_bundle_sha256"
                        ],
                    )
                    self.assertEqual(
                        {"rotation", "translation"},
                        {
                            track["property"]
                            for track in result.retargeted.instance["tracks"]
                        },
                    )
                    animation = result.skeleton["animations"][fixture.p7.clip_id]
                    timelines = {
                        name
                        for bone in animation["bones"].values()
                        for name in bone
                    }
                    self.assertEqual({"rotate", "translate"}, timelines)
                    self.assertEqual("passed", result.report.document["status"])
                    self.assertEqual(
                        "passed", result.verified_export.export_report["status"]
                    )
                    reports.append(report)
                    results.append(result)

            self.assertEqual(1, len({
                report["source"]["projected_bundle_sha256"]
                for report in reports
            }))
            self.assertEqual(1, len({_scale_vector(report) for report in reports}))
            self.assertEqual(3, len({
                report["source"]["target_profile_sha256"]
                for report in reports
            }))
            self.assertEqual(3, len({
                result.p5_bundle.bundle_sha256 for result in results
            }))
            self.assertEqual(3, len({
                result.first_export.bundle_sha256 for result in results
            }))


if __name__ == "__main__":
    unittest.main()
