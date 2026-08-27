"""Persisted-chain end-to-end coverage for P10.6a."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_motion_consumer_admission_commands import (  # noqa: E402
    P10MotionConsumerAdmissionCommandError,
    compile_body_sway_motion_consumer_admission_command,
)
from autospine_workbench.reviewed_motion_bundle_reader import (  # noqa: E402
    VerifiedReviewedMotionBundleReader,
)
from tests.p10_motion_consumer_e2e_helpers import (  # noqa: E402
    MotionConsumerE2EFixture,
)


class P10MotionConsumerAdmissionEndToEndTests(unittest.TestCase):
    def test_real_chain_succeeds_then_seam_head_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = MotionConsumerE2EFixture(Path(temporary))
            with fixture.deterministic_dynamic_seam_backend():
                dynamic = fixture.compile_dynamic_probe()
                probe = dynamic.document["probe"]
                path = fixture.write_probe(probe)
                result = compile_body_sway_motion_consumer_admission_command(
                    fixture.state_root,
                    fixture.project_id,
                    path,
                    dynamic_seam_probe_sha256=dynamic.probe_sha256,
                )
            address = probe["source"]["body_sway_continuous_preview_proof"] \
                ["source"]["amplitude_envelope_candidate"]["source"] \
                ["reviewed_probe_report"]["source"]["p9"]
            bundle = VerifiedReviewedMotionBundleReader(
                fixture.state_root
            ).load(
                fixture.project_id,
                address["motion_instance_v2_sha256"],
                address["bundle_sha256"],
            )

            document = result.document
            admission = document["admission"]
            observed = document["head_observation"]["before"]
            identity = observed["identity"]
            self.assertEqual(
                "setup_local_timeline_compilation_admitted",
                admission["status"],
            )
            self.assertEqual("observed_current", observed["checks"][
                "visual_review_head"
            ])
            self.assertEqual("observed_current", observed["checks"][
                "seam_anchor_review_head"
            ])
            self.assertEqual(
                fixture.visual.approved.revision,
                identity["visual_review"]["revision"],
            )
            self.assertEqual(
                fixture.seam_submission.revision,
                identity["seam_anchor_review"]["revision"],
            )
            self.assertEqual(
                result.admission_sha256,
                document["body_sway_motion_consumer_admission_sha256"],
            )
            self.assertEqual(
                bundle.document("motion-instance-v2.json"),
                probe["source"]["body_sway_continuous_preview_proof"]
                ["source"]["motion_instance_v2"],
            )

            with fixture.deterministic_dynamic_seam_backend():
                fixture.advance_seam_head()
                with self.assertRaises(
                    P10MotionConsumerAdmissionCommandError
                ):
                    compile_body_sway_motion_consumer_admission_command(
                        fixture.state_root,
                        fixture.project_id,
                        path,
                        dynamic_seam_probe_sha256=dynamic.probe_sha256,
                    )


if __name__ == "__main__":
    unittest.main()
