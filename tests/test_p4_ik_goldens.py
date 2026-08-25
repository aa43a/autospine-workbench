"""Approved exact-address regression for the two real P4 IK samples."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.ik_bundle_reader import (  # noqa: E402
    VerifiedIkBundleReader,
)
from autospine_workbench.ik_pipeline import VerifiedIkPipeline  # noqa: E402


GOLDEN_ROOT = ROOT / "tests" / "goldens" / "p4-ik"
SOURCE_KEYS = {
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256", "probes_sha256",
    "visuals_sha256", "bundle_sha256",
}
P4_KEYS = {"profile_sha256", "probes_sha256", "bundle_sha256"}
SUMMARY = {
    "handle_count": 4,
    "evaluated_case_count": 20,
    "not_applicable_case_count": 0,
}
HANDLE_IDS = ("arm.left", "arm.right", "leg.left", "leg.right")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _contracts() -> list[dict]:
    return [_strict_json(path) for path in sorted(GOLDEN_ROOT.glob("*.approved.json"))]


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
    if not isinstance(value, dict):
        raise ValueError("P4 IK golden must be an object")
    return value


def _projection(verified) -> dict:
    profile, probes = verified.profile, verified.probes
    probe_handles = {item["handle_id"]: item for item in probes["handles"]}
    handles = []
    for item in profile["handles"]:
        probe = probe_handles[item["id"]]
        if probe["kinematic_reach"] != item["kinematic_reach"]:
            raise ValueError("P4 profile/probe reach drifted")
        handles.append({
            "id": item["id"],
            "bend_direction": item["bend_direction"],
            "kinematic_reach": item["kinematic_reach"],
        })
    return {
        "format": "autospine-p4-ik-golden",
        "format_version": 1,
        "project_id": verified.project_id,
        "p3_source": verified.source_identities,
        "p4": {
            "profile_sha256": verified.profile_sha256,
            "probes_sha256": verified.probes_sha256,
            "bundle_sha256": verified.bundle_sha256,
        },
        "summary": probes["summary"],
        "handles": handles,
    }


def _tree_snapshot(root: Path):
    directories = []
    files = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            raise ValueError(f"unsupported state entry: {relative}")
    return tuple(sorted(directories)), dict(sorted(files.items()))


class P4IkGoldenTests(unittest.TestCase):
    def test_approved_contracts_are_strict_complete_and_semantic(self) -> None:
        contracts = _contracts()
        self.assertEqual(2, len(contracts))
        self.assertEqual(2, len({item["project_id"] for item in contracts}))
        for item in contracts:
            with self.subTest(project=item["project_id"]):
                self.assertEqual({
                    "format", "format_version", "project_id", "p3_source",
                    "p4", "summary", "handles",
                }, set(item))
                self.assertEqual("autospine-p4-ik-golden", item["format"])
                self.assertEqual(1, item["format_version"])
                self.assertEqual(SOURCE_KEYS, set(item["p3_source"]))
                self.assertEqual(P4_KEYS, set(item["p4"]))
                digests = [*item["p3_source"].values(), *item["p4"].values()]
                self.assertTrue(all(SHA256.fullmatch(value) for value in digests))
                self.assertEqual(SUMMARY, item["summary"])
                self.assertEqual(HANDLE_IDS, tuple(
                    handle["id"] for handle in item["handles"]
                ))
                for handle in item["handles"]:
                    self.assertEqual({
                        "id", "bend_direction", "kinematic_reach",
                    }, set(handle))
                    self.assertIn(handle["bend_direction"], {"positive", "negative"})
                    reach = handle["kinematic_reach"]
                    self.assertEqual({"minimum_px", "maximum_px"}, set(reach))
                    self.assertTrue(all(
                        isinstance(value, float) and math.isfinite(value)
                        for value in reach.values()
                    ))
                    self.assertGreaterEqual(reach["minimum_px"], 0.0)
                    self.assertGreater(reach["maximum_px"], reach["minimum_px"])

    @unittest.skipUnless(
        os.environ.get("AUTOSPINE_VERIFY_REAL_P4_GOLDENS") == "1",
        "real P4 golden verification is explicitly enabled",
    )
    def test_real_bundles_rebuild_and_leave_state_tree_unchanged(self) -> None:
        state_root = ROOT / "workspace"
        before = _tree_snapshot(state_root)
        for approved in _contracts():
            source, p4 = approved["p3_source"], approved["p4"]
            with self.subTest(project=approved["project_id"]):
                rebuilt = VerifiedIkPipeline(state_root).build(
                    approved["project_id"],
                    source["rig_sha256"],
                    source["bundle_sha256"],
                )
                verified = VerifiedIkBundleReader(state_root).load(
                    approved["project_id"],
                    p4["profile_sha256"],
                    p4["bundle_sha256"],
                )
                self.assertEqual(source, rebuilt.input_sha256s)
                self.assertEqual({
                    "profile_sha256": p4["profile_sha256"],
                    "probes_sha256": p4["probes_sha256"],
                }, rebuilt.output_sha256s)
                self.assertEqual(rebuilt.profile, verified.profile)
                self.assertEqual(rebuilt.probes, verified.probes)
                self.assertEqual(approved, _projection(verified))
        self.assertEqual(before, _tree_snapshot(state_root))


if __name__ == "__main__":
    unittest.main()
