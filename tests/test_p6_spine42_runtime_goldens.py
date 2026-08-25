"""Approved official-runtime screenshots for the real P6 exports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.png_rgba import decode_rgba_png  # noqa: E402
from autospine_workbench.spine42_runtime_contract import (  # noqa: E402
    canonical_json_bytes,
    require_runtime_golden,
)


GOLDEN_ROOT = ROOT / "tests" / "goldens" / "p6-spine42"
CONTRACT = GOLDEN_ROOT / "runtime.approved.json"
EXPECTED_CASES = {
    "a.setup": (None, 0.0),
    "a.idle.t1000": ("idle", 1.0),
    "a.wave-left.t0600": ("wave.left", 0.6),
    "b.setup": (None, 0.0),
    "b.idle.t1000": ("idle", 1.0),
    "b.wave-left.t0600": ("wave.left", 0.6),
}


def _strict_json(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate golden key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"non-finite golden value: {value}")

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_constant=nonfinite,
    )
    if type(value) is not dict:
        raise ValueError("P6 runtime golden must be an object")
    return value


def _png(path: Path, expected_sha256: str):
    self_stat = path.lstat()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"approved PNG is not a real file: {path.name}")
    raw = path.read_bytes()
    if len(raw) != self_stat.st_size:
        raise ValueError(f"approved PNG size changed while reading: {path.name}")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError(f"approved PNG SHA-256 differs: {path.name}")
    return decode_rgba_png(raw, source_name=path.name)


def _differing_ratio(left: bytes, right: bytes) -> float:
    if len(left) != len(right) or len(left) % 4:
        raise ValueError("approved RGBA buffers differ in length")
    differing = sum(
        left[offset:offset + 4] != right[offset:offset + 4]
        for offset in range(0, len(left), 4)
    )
    return differing / (len(left) // 4)


class P6Spine42RuntimeGoldenTests(unittest.TestCase):
    def test_contract_is_strict_exact_and_canonicalizable(self) -> None:
        raw = _strict_json(CONTRACT)
        approved = require_runtime_golden(raw)

        self.assertEqual(raw, approved)
        self.assertTrue(canonical_json_bytes(approved))
        self.assertEqual("4.2.119", approved["runtime"]["version"])
        self.assertEqual(
            {"width": 640, "height": 640},
            approved["capture"]["viewport"],
        )
        self.assertEqual(1, approved["capture"]["device_pixel_ratio"])
        self.assertEqual("#20242aff", approved["capture"]["background"])
        cases = {item["id"]: item for item in approved["cases"]}
        self.assertEqual(EXPECTED_CASES, {
            case_id: (item["clip"], item["time_seconds"])
            for case_id, item in cases.items()
        })
        self.assertEqual(6, len({
            item["assets"]["skeleton_sha256"] for item in cases.values()
        }))
        for item in cases.values():
            self.assertEqual({
                "max_differing_pixel_ratio": 0.0,
                "max_mean_absolute_error": 0.0,
                "max_channel_delta": 0,
            }, item["thresholds"])

    def test_approved_pngs_match_hash_size_and_complete_suite(self) -> None:
        approved = require_runtime_golden(_strict_json(CONTRACT))
        cases = {item["id"]: item for item in approved["cases"]}
        expected_names = {
            item["golden"]["path"] for item in cases.values()
        }
        actual_names = {
            path.name for path in GOLDEN_ROOT.glob("*.approved.png")
        }
        self.assertEqual(expected_names, actual_names)

        images = {}
        for case_id, item in cases.items():
            with self.subTest(case=case_id):
                image = _png(
                    GOLDEN_ROOT / item["golden"]["path"],
                    item["golden"]["png_sha256"],
                )
                self.assertEqual((640, 640), (image.width, image.height))
                images[case_id] = image

        for prefix in ("a", "b"):
            setup = images[f"{prefix}.setup"].pixels
            idle = images[f"{prefix}.idle.t1000"].pixels
            wave = images[f"{prefix}.wave-left.t0600"].pixels
            self.assertGreater(_differing_ratio(setup, idle), 0.0001)
            self.assertGreater(_differing_ratio(setup, wave), 0.01)

    def test_each_character_keeps_one_atlas_and_texture_identity(self) -> None:
        approved = require_runtime_golden(_strict_json(CONTRACT))
        cases = {item["id"]: item for item in approved["cases"]}
        character_assets = []
        for prefix in ("a", "b"):
            items = [
                cases[f"{prefix}.setup"],
                cases[f"{prefix}.idle.t1000"],
                cases[f"{prefix}.wave-left.t0600"],
            ]
            atlas = {item["assets"]["atlas_sha256"] for item in items}
            texture = {item["assets"]["texture_sha256"] for item in items}
            self.assertEqual(1, len(atlas))
            self.assertEqual(1, len(texture))
            character_assets.append((atlas, texture))
        self.assertNotEqual(character_assets[0], character_assets[1])


if __name__ == "__main__":
    unittest.main()
