"""Approved exact-address regressions for real P5 motion retargets."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_retarget_bundle_contract import (  # noqa: E402
    build_motion_retarget_bundle_contract,
)
from autospine_workbench.motion_retarget_bundle_reader import (  # noqa: E402
    VerifiedMotionRetargetBundleReader,
)
from autospine_workbench.motion_retarget_pipeline import (  # noqa: E402
    VerifiedMotionRetargetPipeline,
)


GOLDEN = ROOT / "tests" / "goldens" / "p5-motion" / "real-samples.approved.json"
REQUEST_KEYS = {
    "p3_rig_sha256", "p3_bundle_sha256", "p4_profile_sha256",
    "p4_bundle_sha256", "motion_clip_sha256", "motion_bundle_sha256",
}
OUTPUT_KEYS = {
    "target_profile_sha256", "motion_instance_sha256",
    "retarget_run_identity_sha256", "retarget_run_document_sha256",
    "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
}
GATE_KEYS = {
    "summary", "sample_count", "contact_source_count",
    "contact_preserved_count", "mesh_summary", "mesh_status",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _strict_json(path: Path) -> dict:
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate golden key: {key}")
            value[key] = item
        return value

    def nonfinite(value):
        raise ValueError(f"non-finite golden value: {value}")

    document = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_constant=nonfinite,
    )
    if not isinstance(document, dict):
        raise ValueError("P5 motion golden must be an object")
    return document


def _tree_snapshot(root: Path):
    directories, files = [], {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            raise ValueError(f"unsupported state entry: {relative}")
    return tuple(sorted(directories)), dict(sorted(files.items()))


def _projection(result) -> tuple[dict, dict]:
    contract = build_motion_retarget_bundle_contract(
        result.project_id, result.target_profile, result.motion_instance,
        result.retarget_run, result.retarget_report, result.mesh_regression,
    )
    report, mesh = result.retarget_report, result.mesh_regression
    outputs = {
        **result.output_sha256s,
        "retarget_run_identity_sha256": (
            result.motion_instance["source"]["retarget_run_identity_sha256"]
        ),
        "bundle_sha256": contract.bundle_sha256,
    }
    gate = {
        "summary": result.summary,
        "sample_count": report["sampler"]["sample_count"],
        "contact_source_count": report["contacts"]["source_count"],
        "contact_preserved_count": report["contacts"]["preserved_count"],
        "mesh_summary": mesh["summary"],
        "mesh_status": mesh["status"],
    }
    return outputs, gate


class P5MotionGoldenTests(unittest.TestCase):
    def test_approved_contract_is_strict_complete_and_semantic(self) -> None:
        approved = _strict_json(GOLDEN)
        self.assertEqual({"format", "format_version", "cases"}, set(approved))
        self.assertEqual("autospine-p5-motion-golden", approved["format"])
        self.assertEqual(1, approved["format_version"])
        cases = approved["cases"]
        self.assertIsInstance(cases, list)
        self.assertEqual(4, len(cases))
        self.assertEqual(4, len({
            (item["project_id"], item["clip_id"]) for item in cases
        }))
        self.assertEqual({"seethrough_output", "seethrough_output_5"}, {
            item["project_id"] for item in cases
        })
        for item in cases:
            with self.subTest(project=item["project_id"], clip=item["clip_id"]):
                self.assertEqual(
                    {"project_id", "clip_id", "request", "outputs", "gate"},
                    set(item),
                )
                self.assertIn(item["clip_id"], {"idle", "wave.left"})
                self.assertEqual(REQUEST_KEYS, set(item["request"]))
                self.assertEqual(OUTPUT_KEYS, set(item["outputs"]))
                self.assertTrue(all(
                    SHA256.fullmatch(value)
                    for value in (*item["request"].values(), *item["outputs"].values())
                ))
                gate = item["gate"]
                self.assertEqual(GATE_KEYS, set(gate))
                self.assertEqual(41, gate["sample_count"])
                self.assertEqual(2, gate["contact_source_count"])
                self.assertEqual(2, gate["contact_preserved_count"])
                self.assertEqual("passed", gate["mesh_status"])
                self.assertIn(gate["mesh_summary"], {"attachments=2", "reviewed-noop"})

    @unittest.skipUnless(
        os.environ.get("AUTOSPINE_VERIFY_REAL_P5_GOLDENS") == "1",
        "real P5 golden verification is explicitly enabled",
    )
    def test_real_bundles_rebuild_and_leave_state_tree_unchanged(self) -> None:
        state_root = ROOT / "workspace"
        before = _tree_snapshot(state_root)
        for approved in _strict_json(GOLDEN)["cases"]:
            request, expected = approved["request"], approved["outputs"]
            with self.subTest(
                project=approved["project_id"], clip=approved["clip_id"]
            ):
                rebuilt = VerifiedMotionRetargetPipeline(state_root).build(
                    approved["project_id"],
                    request["p3_rig_sha256"], request["p3_bundle_sha256"],
                    request["p4_profile_sha256"], request["p4_bundle_sha256"],
                    request["motion_clip_sha256"], request["motion_bundle_sha256"],
                )
                outputs, gate = _projection(rebuilt)
                self.assertEqual(expected, outputs)
                self.assertEqual(approved["gate"], gate)
                verified = VerifiedMotionRetargetBundleReader(state_root).load(
                    approved["project_id"], expected["motion_instance_sha256"],
                    expected["bundle_sha256"],
                )
                self.assertEqual(rebuilt.target_profile, verified.target_profile)
                self.assertEqual(rebuilt.motion_instance, verified.motion_instance)
                self.assertEqual(rebuilt.retarget_report, verified.retarget_report)
                self.assertEqual(rebuilt.mesh_regression, verified.mesh_regression)
        self.assertEqual(before, _tree_snapshot(state_root))


if __name__ == "__main__":
    unittest.main()
