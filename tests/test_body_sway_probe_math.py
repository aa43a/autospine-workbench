"""P10.2 overlay, v2 sampling, combination, and loop audit tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import math
import unittest

from autospine_workbench.body_sway_probe_math import (
    BodySwayPoseSample,
    BodySwayProbeMathError,
    audit_body_sway_loop,
    sample_body_sway_pose,
)
from tests.body_sway_probe_math_helpers import (
    amplitudes,
    phases,
    timing,
    tracks,
)


class BodySwayProbeMathTests(unittest.TestCase):
    def sample(
        self, *, spec=None, authored=None, tick=0, cycles=1,
        amplitude_rows=None, phase_rows=None,
    ):
        selected = timing() if spec is None else spec
        return sample_body_sway_pose(
            selected,
            tracks(selected["duration_ticks"])
            if authored is None else authored,
            tick=tick,
            cycles=cycles,
            per_bone_amplitude_deg=(
                amplitudes() if amplitude_rows is None else amplitude_rows
            ),
            per_bone_phase_fraction=(
                phases() if phase_rows is None else phase_rows
            ),
        )

    def test_quarter_cycle_is_clockwise_additive_without_spine_reflection(self):
        amplitude_rows = amplitudes((0.0, 0.0, 0.0, 2.0))
        phase_rows = phases((0.0, 0.0, 0.0, 0.0))
        sample = self.sample(
            tick=250_000, amplitude_rows=amplitude_rows,
            phase_rows=phase_rows,
        )
        base = dict(sample.base_rotation_deg)
        overlay = dict(sample.overlay_rotation_deg)
        combined = dict(sample.combined_rotation_deg)
        self.assertEqual(2.0, base["neck-head"])
        self.assertEqual(2.0, overlay["neck-head"])
        self.assertEqual(4.0, combined["neck-head"])
        self.assertEqual((5.0, -2.0), sample.root_translation_xy)
        self.assertGreater(combined["neck-head"], 0.0)

    def test_missing_target_rotation_is_zero_and_other_base_tracks_survive(self):
        authored = tracks()
        authored.append({
            "bone_id": "thigh.left", "property": "rotation",
            "keys": [
                {"tick": 0, "value": 1.0},
                {"tick": 500_000, "value": 3.0},
                {"tick": 1_000_000, "value": 1.0},
            ],
        })
        sample = self.sample(authored=authored, tick=250_000)
        base = dict(sample.base_rotation_deg)
        combined = dict(sample.combined_rotation_deg)
        self.assertEqual(0.0, base["pelvis-spine"])
        self.assertEqual(2.0, base["thigh.left"])
        self.assertEqual(2.0, combined["thigh.left"])

    def test_arbitrary_phase_and_sixty_four_cycle_endpoint_copy(self):
        amplitude_rows = amplitudes((1.0, 2.0, 3.0, 4.0))
        phase_rows = phases((0.1, 0.2, 0.3, 0.999999999))
        start = self.sample(
            tick=0, cycles=64, amplitude_rows=amplitude_rows,
            phase_rows=phase_rows,
        )
        end = self.sample(
            tick=1_000_000, cycles=64, amplitude_rows=amplitude_rows,
            phase_rows=phase_rows,
        )
        self.assertEqual(start.overlay_rotation_deg, end.overlay_rotation_deg)
        self.assertTrue(all(
            math.isfinite(value)
            for _bone_id, value in start.overlay_rotation_deg
        ))

    def test_linear_sampling_and_nine_digit_quantization_are_deterministic(self):
        spec = timing(100_003, loop=False)
        authored = tracks(100_003, authored_tick=33_333, rotation_end=1.0,
                          root_end=(1.0, 2.0))
        amplitude_rows = amplitudes((0.0, 0.0, 0.0, 1.23456789123))
        phase_rows = phases((0.0, 0.0, 0.0, 0.123456789))
        before = deepcopy((spec, authored, amplitude_rows, phase_rows))
        first = self.sample(
            spec=spec, authored=authored, tick=66_667,
            amplitude_rows=amplitude_rows, phase_rows=phase_rows,
        )
        second = self.sample(
            spec=deepcopy(spec), authored=deepcopy(authored), tick=66_667,
            amplitude_rows=deepcopy(amplitude_rows),
            phase_rows=deepcopy(phase_rows),
        )
        self.assertEqual(first, second)
        self.assertEqual(before, (spec, authored, amplitude_rows, phase_rows))
        for collection in (
            first.base_rotation_deg,
            first.overlay_rotation_deg,
            first.combined_rotation_deg,
        ):
            for _bone_id, value in collection:
                self.assertEqual(round(value, 9), value)
        with self.assertRaises(FrozenInstanceError):
            first.tick = 0  # type: ignore[misc]

    def test_effective_subnanodegree_amplitude_uses_output_quantization(self):
        sample = self.sample(
            tick=250_000,
            amplitude_rows=amplitudes((0.0, 0.0, 0.0, 0.0000000006)),
            phase_rows=phases((0.0, 0.0, 0.0, 0.0)),
        )
        self.assertEqual(0.000000001, sample.overlay_rotation_deg[-1][1])

    def test_loop_requires_all_numeric_endpoints_to_close(self):
        spec = timing(loop=True)
        start = self.sample(spec=spec, tick=0)
        end = self.sample(spec=spec, tick=1_000_000)
        audit = audit_body_sway_loop(spec, start, end)
        self.assertEqual("closed", audit.status)
        self.assertEqual((), audit.reason_codes)
        self.assertFalse(audit.to_dict()["visual_safety_claimed"])

        open_tracks = tracks(rotation_end=5.0, root_end=(1.0, 0.0))
        open_end = self.sample(spec=spec, authored=open_tracks,
                               tick=1_000_000)
        rejected = audit_body_sway_loop(spec, start, open_end)
        self.assertEqual("rejected", rejected.status)
        self.assertIn("base_rotation_not_closed", rejected.reason_codes)
        self.assertIn("combined_rotation_not_closed", rejected.reason_codes)
        self.assertIn("root_translation_not_closed", rejected.reason_codes)

    def test_non_loop_only_requires_overlay_closure(self):
        spec = timing(loop=False)
        authored = tracks(rotation_end=5.0, root_end=(1.0, 0.0))
        start = self.sample(spec=spec, authored=authored, tick=0)
        end = self.sample(spec=spec, authored=authored, tick=1_000_000)
        audit = audit_body_sway_loop(spec, start, end)
        self.assertEqual("closed", audit.status)
        self.assertTrue(audit.overlay_closed)
        self.assertFalse(audit.base_rotation_closed)
        self.assertFalse(audit.combined_rotation_closed)
        self.assertFalse(audit.root_translation_closed)
        self.assertEqual((), audit.reason_codes)

        forged_overlay = replace(
            end,
            overlay_rotation_deg=end.overlay_rotation_deg[:-1] +
            (("neck-head", 1.0),),
        )
        rejected = audit_body_sway_loop(spec, start, forged_overlay)
        self.assertEqual("rejected", rejected.status)
        self.assertEqual(("overlay_not_closed",), rejected.reason_codes)

    def test_invalid_tick_amplitude_phase_and_bone_inventory_fail_closed(self):
        cases = []
        for tick in (-1, 1_000_001, True):
            cases.append({"tick": tick})
        for value in (-1.0, 10.0001, float("nan"), float("inf"), True):
            changed = amplitudes()
            changed[0]["value"] = value
            cases.append({"amplitude_rows": changed})
        cases.append({"amplitude_rows": amplitudes((0.0, 0.0, 0.0, 0.0))})
        cases.append({
            "amplitude_rows": amplitudes((0.0, 0.0, 0.0, 0.0000000004)),
        })
        mismatched = phases()
        mismatched.reverse()
        cases.append({"phase_rows": mismatched})
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(
                BodySwayProbeMathError
            ):
                self.sample(**arguments)

    def test_root_translation_and_loop_audit_inputs_fail_closed(self):
        missing_root = tracks()[:1]
        with self.assertRaisesRegex(BodySwayProbeMathError, "root translation"):
            self.sample(authored=missing_root)
        sample = self.sample(tick=0)
        with self.assertRaises(BodySwayProbeMathError):
            audit_body_sway_loop(timing(), sample, sample)
        with self.assertRaises(BodySwayProbeMathError):
            audit_body_sway_loop(
                timing(), sample, object()  # type: ignore[arg-type]
            )

    def test_to_dict_is_detached_and_complete(self):
        sample = self.sample(tick=250_000)
        document = sample.to_dict()
        self.assertEqual(250_000, document["tick"])
        document["combined_rotation_deg"].clear()
        self.assertTrue(sample.to_dict()["combined_rotation_deg"])
        self.assertIsInstance(sample, BodySwayPoseSample)


if __name__ == "__main__":
    unittest.main()
