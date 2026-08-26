"""Exact parity and admission tests for the prepared body-sway sampler."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_probe_math import (  # noqa: E402
    BodySwayProbeMathError,
    sample_body_sway_pose,
)
from autospine_workbench.body_sway_probe_sampler import (  # noqa: E402
    prepare_body_sway_sampler,
)
from tests.body_sway_probe_math_helpers import (  # noqa: E402
    amplitudes,
    phases,
    timing,
    tracks,
)


def _prepare(spec, authored, amplitude_rows, phase_rows, cycles):
    return prepare_body_sway_sampler(
        spec,
        authored,
        cycles=cycles,
        per_bone_amplitude_deg=amplitude_rows,
        per_bone_phase_fraction=phase_rows,
    )


def _legacy(spec, authored, amplitude_rows, phase_rows, cycles, tick):
    return sample_body_sway_pose(
        spec,
        authored,
        tick=tick,
        cycles=cycles,
        per_bone_amplitude_deg=amplitude_rows,
        per_bone_phase_fraction=phase_rows,
    )


class PreparedBodySwaySamplerTests(unittest.TestCase):
    def setUp(self):
        self.spec = timing(100_003, loop=False)
        self.authored = tracks(
            100_003,
            authored_tick=33_333,
            rotation_end=-1.25,
            root_end=(3.5, -7.25),
        )
        self.authored.append({
            "bone_id": "thigh.left",
            "property": "rotation",
            "keys": [
                {"tick": 0, "value": -2.0},
                {"tick": 50_001, "value": 7.5},
                {"tick": 100_003, "value": 1.25},
            ],
        })
        self.amplitude_rows = amplitudes((0.5, 2.25, 0.75, 4.125))
        self.phase_rows = phases((0.0, 0.123456789, 0.5, 0.999999999))
        self.cycles = 7

    def prepared(self):
        return _prepare(
            self.spec,
            self.authored,
            self.amplitude_rows,
            self.phase_rows,
            self.cycles,
        )

    def test_hundreds_of_ticks_match_legacy_field_for_field(self):
        sampler = self.prepared()
        ticks = {0, 1, 33_332, 33_333, 33_334, 50_001, 100_002, 100_003}
        value = 17
        for _index in range(700):
            value = (value * 48_271 + 31) % 100_004
            ticks.add(value)
        for tick in sorted(ticks):
            with self.subTest(tick=tick):
                self.assertEqual(
                    _legacy(
                        self.spec,
                        self.authored,
                        self.amplitude_rows,
                        self.phase_rows,
                        self.cycles,
                        tick,
                    ),
                    sampler.sample(tick),
                )

    def test_duration_overlay_copy_and_scalar_vector_keys_match(self):
        sampler = self.prepared()
        start, end = sampler.sample(0), sampler.sample(100_003)
        self.assertEqual(start.overlay_rotation_deg, end.overlay_rotation_deg)
        self.assertEqual(
            _legacy(
                self.spec,
                self.authored,
                self.amplitude_rows,
                self.phase_rows,
                self.cycles,
                50_000,
            ),
            sampler.sample(50_000),
        )
        self.assertIsInstance(dict(end.base_rotation_deg)["neck-head"], float)
        self.assertEqual((3.5, -7.25), end.root_translation_xy)

    def test_inputs_are_detached_and_sampler_is_frozen_and_deterministic(self):
        before = deepcopy((
            self.spec,
            self.authored,
            self.amplitude_rows,
            self.phase_rows,
        ))
        sampler = self.prepared()
        expected = sampler.sample(77_777)
        self.authored[0]["keys"][0]["value"] = 999.0
        self.amplitude_rows[0]["value"] = 9.0
        self.phase_rows[0]["value"] = 0.25
        self.spec["duration_ticks"] = 1
        self.assertEqual(expected, sampler.sample(77_777))
        self.assertEqual(100_003, sampler.duration_ticks)
        with self.assertRaises(FrozenInstanceError):
            sampler._duration = 1  # type: ignore[misc]
        self.assertNotEqual(before, (
            self.spec,
            self.authored,
            self.amplitude_rows,
            self.phase_rows,
        ))

    def test_static_normalization_runs_once_for_many_samples(self):
        import autospine_workbench.body_sway_probe_sampler as module

        with patch.object(
            module, "normalize_tracks", wraps=module.normalize_tracks,
        ) as normalize:
            sampler = self.prepared()
            for tick in range(0, 100_004, 997):
                sampler.sample(tick)
        self.assertEqual(1, normalize.call_count)

    def test_invalid_ticks_and_static_inputs_fail_closed(self):
        sampler = self.prepared()
        for tick in (-1, 100_004, True, 1.5):
            with self.subTest(tick=tick), self.assertRaises(
                BodySwayProbeMathError
            ):
                sampler.sample(tick)  # type: ignore[arg-type]

        cases = []
        wrong_timing = timing(100_003)
        wrong_timing["ticks_per_second"] = 30
        cases.append((wrong_timing, self.authored, self.amplitude_rows,
                      self.phase_rows, self.cycles))
        cases.append((self.spec, list(reversed(self.authored)),
                      self.amplitude_rows, self.phase_rows, self.cycles))
        cases.append((self.spec, self.authored,
                      amplitudes((0.0, 0.0, 0.0, 0.0)),
                      self.phase_rows, self.cycles))
        cases.append((self.spec, self.authored, self.amplitude_rows,
                      list(reversed(self.phase_rows)), self.cycles))
        cases.append((self.spec, self.authored, self.amplitude_rows,
                      self.phase_rows, True))
        for spec, authored, amplitude_rows, phase_rows, cycles in cases:
            with self.subTest(cycles=cycles), self.assertRaises(
                BodySwayProbeMathError
            ):
                _prepare(
                    spec, authored, amplitude_rows, phase_rows, cycles,
                )

    def test_module_remains_small(self):
        path = SRC / "autospine_workbench" / "body_sway_probe_sampler.py"
        self.assertLess(
            len(path.read_text(encoding="utf-8").splitlines()), 300,
        )


if __name__ == "__main__":
    unittest.main()
