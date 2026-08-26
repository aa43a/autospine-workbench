"""Internal P10.3 sampled-linear projection tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_preview_projection import (  # noqa: E402
    BodySwayPreviewProjectionError,
    compile_body_sway_preview_projection,
)
from autospine_workbench.body_sway_preview_profile import (  # noqa: E402
    PROJECTION_DIGEST_DOMAIN,
)
from autospine_workbench.body_sway_probe_sampler import (  # noqa: E402
    prepare_body_sway_sampler,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture  # noqa: E402


class BodySwayPreviewProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = BodySwayPreviewFixture(Path(cls.temporary.name))
        cls.projection = compile_body_sway_preview_projection(
            cls.fixture.preview_inputs
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_is_deterministic_frozen_copy_isolated_and_internal_domain(self):
        second = compile_body_sway_preview_projection(
            self.fixture.preview_inputs
        )
        self.assertEqual(self.projection, second)
        self.assertEqual(PROJECTION_DIGEST_DOMAIN,
                         self.projection.document["domain"])
        changed = self.projection.document
        changed["rotation_tracks"].clear()
        self.assertTrue(self.projection.rotation_tracks)
        with self.assertRaises(FrozenInstanceError):
            self.projection._canonical_json = "{}"  # type: ignore[misc]

    def test_every_preview_key_equals_the_exact_p10_sampler(self):
        inputs = self.fixture.preview_inputs
        motion = inputs.probe_inputs.motion_instance_v2
        parameters = inputs.selection["parameters"]
        sampler = prepare_body_sway_sampler(
            inputs.timing, motion["tracks"],
            cycles=parameters["cycles"],
            per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        tracks = {row["bone_id"]: row for row in self.projection.rotation_tracks}
        for index, tick in enumerate(self.projection.sample_ticks):
            expected = dict(sampler.sample(tick).combined_rotation_deg)
            self.assertEqual(set(expected), set(tracks))
            for bone_id, value in expected.items():
                self.assertEqual(
                    {"tick": tick, "value": value},
                    tracks[bone_id]["keys"][index],
                )

    def test_public_metadata_is_bounded_and_binds_probe_stream(self):
        metadata = self.projection.public_metadata
        report = self.fixture.report.document
        self.assertEqual(self.projection.sha256,
                         metadata["projection_sha256"])
        self.assertEqual(report["schedule"]["sample_count"],
                         metadata["sample_count"])
        self.assertEqual(report["sample_stream"]["sample_stream_sha256"],
                         metadata["probe_sample_stream_sha256"])
        self.assertEqual("sampled-linear",
                         metadata["rotation_interpolation"])

    def test_sample_ceiling_fails_before_large_projection_allocation(self):
        oversized = tuple(range(4097))
        with patch(
            "autospine_workbench.body_sway_preview_projection."
            "build_body_sway_sample_ticks",
            return_value=oversized,
        ), self.assertRaisesRegex(
            BodySwayPreviewProjectionError, "sample count"
        ):
            compile_body_sway_preview_projection(
                self.fixture.preview_inputs
            )

    def test_spoofed_input_type_is_rejected(self):
        before = deepcopy(self.fixture.preview_inputs.report)
        with self.assertRaisesRegex(
            BodySwayPreviewProjectionError, "exact preview"
        ):
            compile_body_sway_preview_projection(object())  # type: ignore[arg-type]
        self.assertEqual(before, self.fixture.preview_inputs.report)


if __name__ == "__main__":
    unittest.main()
