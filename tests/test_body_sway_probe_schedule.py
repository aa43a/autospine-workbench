"""P10.2 exact Fraction-based body-sway sample schedule tests."""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import math
import unittest
from unittest.mock import patch

from autospine_workbench.body_sway_probe_math import (
    BodySwayProbeMathError,
    build_body_sway_sample_ticks,
)
from autospine_workbench.body_sway_probe_profile import (
    body_sway_probe_profile,
)
from tests.body_sway_probe_math_helpers import phases, timing, tracks


class BodySwayProbeScheduleTests(unittest.TestCase):
    def schedule(self, *, spec=None, authored=None, cycles=1, phase_rows=None):
        selected = timing(200_000) if spec is None else spec
        return build_body_sway_sample_ticks(
            selected,
            tracks(selected["duration_ticks"], authored_tick=33_333)
            if authored is None else authored,
            cycles=cycles,
            per_bone_phase_fraction=phases((0.0, 0.0, 0.0, 0.0))
            if phase_rows is None else phase_rows,
        )

    def test_profile_is_exact_unique_and_detached(self):
        expected = {
            "id": "body-sway-structural-probe",
            "version": "1.0.0",
            "config": {
                "fixed_sample_step_ticks": 50_000,
                "uniform_samples_per_cycle": 32,
                "max_sample_count": 65_536,
                "numeric_precision_decimals": 9,
                "mesh_thresholds": {
                    "min_signed_area_ratio": 0.02,
                    "max_signed_area_ratio": 20.0,
                    "max_edge_stretch_ratio": 3.0,
                },
            },
        }
        first, second = body_sway_probe_profile(), body_sway_probe_profile()
        self.assertEqual(expected, first)
        first["config"]["fixed_sample_step_ticks"] = 1
        self.assertEqual(expected, second)

    def test_schedule_unions_boundaries_authored_20hz_and_uniform_ticks(self):
        result = self.schedule()
        self.assertEqual(tuple(sorted(set(result))), result)
        self.assertEqual((0, 200_000), (result[0], result[-1]))
        self.assertIn(33_333, result)
        for tick in range(0, 200_001, 50_000):
            self.assertIn(tick, result)
        for index in range(33):
            self.assertIn(index * 6_250, result)

    def test_non_divisible_zero_and_extrema_landmarks_are_bracketed(self):
        duration = 100_003
        spec = timing(duration)
        rows = phases((0.1, 0.1, 0.1, 0.1))
        result = self.schedule(spec=spec, phase_rows=rows)
        # phase=1/10 makes q=1..4 respectively +peak, zero, -peak, zero.
        landmarks = (
            Fraction(duration * 3, 20),
            Fraction(duration * 2, 5),
            Fraction(duration * 13, 20),
            Fraction(duration * 9, 10),
        )
        self.assertEqual(Fraction(300_009, 20), landmarks[0])
        for landmark in landmarks:
            self.assertIn(landmark.numerator // landmark.denominator, result)
            self.assertIn(
                -(-landmark.numerator // landmark.denominator), result
            )

    def test_sixty_four_cycles_keep_at_least_32_nominal_samples_each(self):
        duration = 6_400_003
        result = self.schedule(
            spec=timing(duration), cycles=64,
            phase_rows=phases((0.01, 0.2, 0.4, 0.9)),
        )
        self.assertGreaterEqual(len(result), 64 * 32 + 1)
        for index in (1, 31, 32, 1024, 2047):
            nominal = Fraction(duration * index, 64 * 32)
            self.assertTrue(
                {nominal.numerator // nominal.denominator,
                 -(-nominal.numerator // nominal.denominator)} <= set(result)
            )

    def test_determinism_and_inputs_are_not_mutated(self):
        spec = timing(200_000)
        authored = tracks(200_000, authored_tick=33_333)
        phase_rows = phases((0.1, 0.2, 0.3, 0.4))
        before = deepcopy((spec, authored, phase_rows))
        first = self.schedule(
            spec=spec, authored=authored, cycles=3, phase_rows=phase_rows,
        )
        second = self.schedule(
            spec=deepcopy(spec), authored=deepcopy(authored), cycles=3,
            phase_rows=deepcopy(phase_rows),
        )
        self.assertEqual(first, second)
        self.assertEqual(before, (spec, authored, phase_rows))

    def test_profile_sample_limit_fails_closed(self):
        with patch(
            "autospine_workbench.body_sway_probe_math.MAX_SAMPLE_COUNT", 10
        ), self.assertRaisesRegex(BodySwayProbeMathError, "sample count"):
            self.schedule()

    def test_duration_must_represent_uniform_samples_without_tick_aliasing(self):
        with self.assertRaisesRegex(BodySwayProbeMathError, "32 unique"):
            self.schedule(
                spec=timing(1_000),
                authored=tracks(1_000, authored_tick=500),
                cycles=64,
            )

    def test_invalid_timing_cycles_and_parameter_bones_fail_closed(self):
        cases = []
        wrong_rate = timing(200_000)
        wrong_rate["ticks_per_second"] = 1_000
        cases.append((wrong_rate, tracks(200_000), 1, phases()))
        wrong_loop = timing(200_000)
        wrong_loop["loop"] = 1
        cases.append((wrong_loop, tracks(200_000), 1, phases()))
        for cycles in (0, 65, True):
            cases.append((timing(200_000), tracks(200_000), cycles, phases()))
        for value in (-0.1, 1.0, float("nan"), float("inf"), True):
            changed = phases()
            changed[0]["value"] = value
            cases.append((timing(200_000), tracks(200_000), 1, changed))
        wrong_bone = phases()
        wrong_bone[0]["bone_id"] = "thigh.left"
        cases.append((timing(200_000), tracks(200_000), 1, wrong_bone))
        reordered = phases()
        reordered.reverse()
        cases.append((timing(200_000), tracks(200_000), 1, reordered))
        for spec, authored, cycles, phase_rows in cases:
            with self.subTest(cycles=cycles, phase_rows=phase_rows), \
                    self.assertRaises(BodySwayProbeMathError):
                build_body_sway_sample_ticks(
                    spec, authored, cycles=cycles,
                    per_bone_phase_fraction=phase_rows,
                )

    def test_invalid_authored_keys_tracks_and_numbers_fail_closed(self):
        variants = []
        reversed_tracks = tracks(200_000)
        reversed_tracks.reverse()
        variants.append(reversed_tracks)
        duplicate_tick = tracks(200_000)
        duplicate_tick[0]["keys"][1]["tick"] = 0
        variants.append(duplicate_tick)
        out_of_order = tracks(200_000)
        out_of_order[0]["keys"][1]["tick"] = 200_000
        variants.append(out_of_order)
        outside_tick = tracks(200_000)
        outside_tick[0]["keys"][-1]["tick"] = 200_001
        variants.append(outside_tick)
        nonfinite = tracks(200_000)
        nonfinite[0]["keys"][1]["value"] = math.nan
        variants.append(nonfinite)
        bool_tick = tracks(200_000)
        bool_tick[0]["keys"][1]["tick"] = True
        variants.append(bool_tick)
        no_root = tracks(200_000)[:1]
        variants.append(no_root)
        for authored in variants:
            with self.subTest(authored=authored), self.assertRaises(
                BodySwayProbeMathError
            ):
                self.schedule(authored=authored)


if __name__ == "__main__":
    unittest.main()
