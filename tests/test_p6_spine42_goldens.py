"""Approved exact-address regressions for six real P6 Spine exports."""

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

from autospine_workbench.spine42_bundle_integrity import (  # noqa: E402
    VerifiedSpine42BundleReader,
)
from autospine_workbench.spine42_pipeline import (  # noqa: E402
    VerifiedSpine42Pipeline,
)


GOLDEN = ROOT / "tests" / "goldens" / "p6-spine42" / "real-exports.approved.json"
P5_GOLDEN = ROOT / "tests" / "goldens" / "p5-motion" / "real-samples.approved.json"
REQUEST_KEYS = {
    "p3_rig_sha256", "p3_bundle_sha256",
    "motion_instance_sha256", "motion_bundle_sha256",
}
OUTPUT_KEYS = {
    "skeleton_json_sha256", "atlas_sha256", "png_sha256",
    "run_identity_sha256", "run_document_sha256",
    "report_sha256", "bundle_sha256",
}
CHECK_KEYS = {
    "adapter-profile", "attachment-atlas-binding", "atlas-png-geometry",
    "source-image-binding", "motion-binding",
}
METRIC_KEYS = {
    "bones", "slots", "attachments", "animations", "events",
    "atlas_regions", "atlas_width", "atlas_height", "source_images",
}
EXPECTED_CASES = {
    (project, mode, clip)
    for project in ("seethrough_output", "seethrough_output_5")
    for mode, clip in (
        ("setup-only", None), ("motion", "idle"), ("motion", "wave.left")
    )
}
PROJECT_METRICS = {
    "seethrough_output": {
        "bones": 17, "slots": 25, "attachments": 25,
        "atlas_regions": 25, "atlas_width": 1166,
        "atlas_height": 1227, "source_images": 25,
    },
    "seethrough_output_5": {
        "bones": 17, "slots": 20, "attachments": 20,
        "atlas_regions": 20, "atlas_width": 2371,
        "atlas_height": 2408, "source_images": 20,
    },
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


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
        raise ValueError("P6 Spine export golden must be an object")
    return value


def _tree_snapshot(root: Path):
    directories, files = [], {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or _is_junction(path):
            raise ValueError(f"state tree contains an alias: {relative}")
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            raise ValueError(f"unsupported state entry: {relative}")
    return tuple(sorted(directories)), dict(sorted(files.items()))


def _is_junction(path: Path) -> bool:
    predicate = getattr(path, "is_junction", None)
    return bool(callable(predicate) and predicate())


def _summary(mode: str, clip: str | None, metrics: dict) -> str:
    names = ("bones", "slots", "attachments", "animations", "events")
    counts = ";".join(f"{name}={metrics[name]}" for name in names)
    return f"mode={mode};clip={'none' if clip is None else clip};{counts}"


def _projection(result) -> dict:
    p5 = result.p5_source
    request = {
        "p3_rig_sha256": result.p3_rig_sha256,
        "p3_bundle_sha256": result.p3_bundle_sha256,
        "motion_instance_sha256": (
            None if p5 is None else p5["motion_instance_sha256"]
        ),
        "motion_bundle_sha256": None if p5 is None else p5["bundle_sha256"],
    }
    report = result.export_report
    metrics = report["metrics"]
    gate = {
        "status": report["status"],
        "summary": _summary(result.mode, result.clip_id, metrics),
        "checks": {item["id"]: item["status"] for item in report["checks"]},
        "metrics": metrics,
    }
    return {
        "project_id": result.project_id,
        "mode": result.mode,
        "clip_id": result.clip_id,
        "request": request,
        "outputs": result.contract_identities,
        "gate": gate,
    }


class P6Spine42GoldenTests(unittest.TestCase):
    def test_approved_contract_is_strict_complete_and_semantic(self) -> None:
        approved = _strict_json(GOLDEN)
        self.assertEqual({"format", "format_version", "cases"}, set(approved))
        self.assertEqual("autospine-p6-spine42-golden", approved["format"])
        self.assertEqual(1, approved["format_version"])
        cases = approved["cases"]
        self.assertIsInstance(cases, list)
        self.assertEqual(6, len(cases))
        self.assertEqual(EXPECTED_CASES, {
            (item["project_id"], item["mode"], item["clip_id"])
            for item in cases
        })
        for item in cases:
            with self.subTest(project=item["project_id"], clip=item["clip_id"]):
                self._require_case(item)

        for project in PROJECT_METRICS:
            project_cases = [item for item in cases if item["project_id"] == project]
            self.assertEqual(1, len({
                (
                    item["request"]["p3_rig_sha256"],
                    item["request"]["p3_bundle_sha256"],
                )
                for item in project_cases
            }))
            self.assertEqual(1, len({
                item["outputs"]["atlas_sha256"] for item in project_cases
            }))
            self.assertEqual(1, len({
                item["outputs"]["png_sha256"] for item in project_cases
            }))
        for field in OUTPUT_KEYS - {"atlas_sha256", "png_sha256"}:
            self.assertEqual(6, len({item["outputs"][field] for item in cases}))

    def _require_case(self, item: dict) -> None:
        self.assertEqual(
            {"project_id", "mode", "clip_id", "request", "outputs", "gate"},
            set(item),
        )
        request, outputs, gate = item["request"], item["outputs"], item["gate"]
        self.assertEqual(REQUEST_KEYS, set(request))
        self.assertEqual(OUTPUT_KEYS, set(outputs))
        self.assertTrue(all(SHA256.fullmatch(value) for value in outputs.values()))
        self.assertTrue(SHA256.fullmatch(request["p3_rig_sha256"]))
        self.assertTrue(SHA256.fullmatch(request["p3_bundle_sha256"]))
        motion_values = (
            request["motion_instance_sha256"], request["motion_bundle_sha256"]
        )
        self.assertEqual(item["mode"] == "motion", all(
            isinstance(value, str) and SHA256.fullmatch(value)
            for value in motion_values
        ))
        self.assertEqual(item["mode"] == "setup-only", all(
            value is None for value in motion_values
        ))
        self.assertEqual({"status", "summary", "checks", "metrics"}, set(gate))
        self.assertEqual("passed", gate["status"])
        self.assertEqual(CHECK_KEYS, set(gate["checks"]))
        self.assertEqual(METRIC_KEYS, set(gate["metrics"]))
        expected_metrics = {
            **PROJECT_METRICS[item["project_id"]],
            "animations": 0 if item["mode"] == "setup-only" else 1,
            "events": 0 if item["mode"] == "setup-only" else 4,
        }
        self.assertEqual(expected_metrics, gate["metrics"])
        expected_motion = "not_applicable" if item["mode"] == "setup-only" \
            else "passed"
        self.assertEqual(expected_motion, gate["checks"]["motion-binding"])
        self.assertTrue(all(
            status == "passed" for name, status in gate["checks"].items()
            if name != "motion-binding"
        ))
        self.assertEqual(
            _summary(item["mode"], item["clip_id"], gate["metrics"]),
            gate["summary"],
        )

    def test_motion_requests_match_the_pinned_p5_golden_chain(self) -> None:
        p5_cases = {
            (item["project_id"], item["clip_id"]): item
            for item in _strict_json(P5_GOLDEN)["cases"]
        }
        for item in _strict_json(GOLDEN)["cases"]:
            if item["mode"] != "motion":
                continue
            with self.subTest(project=item["project_id"], clip=item["clip_id"]):
                p5 = p5_cases[(item["project_id"], item["clip_id"])]
                request = item["request"]
                self.assertEqual(
                    p5["request"]["p3_rig_sha256"], request["p3_rig_sha256"]
                )
                self.assertEqual(
                    p5["request"]["p3_bundle_sha256"], request["p3_bundle_sha256"]
                )
                self.assertEqual(
                    p5["outputs"]["motion_instance_sha256"],
                    request["motion_instance_sha256"],
                )
                self.assertEqual(
                    p5["outputs"]["bundle_sha256"], request["motion_bundle_sha256"]
                )

    @unittest.skipUnless(
        os.environ.get("AUTOSPINE_VERIFY_REAL_P6_GOLDENS") == "1",
        "real P6 Spine golden verification is explicitly enabled",
    )
    def test_real_bundles_rebuild_and_leave_state_tree_unchanged(self) -> None:
        state_root = ROOT / "workspace"
        before = _tree_snapshot(state_root)
        for approved in _strict_json(GOLDEN)["cases"]:
            outputs = approved["outputs"]
            with self.subTest(
                project=approved["project_id"], clip=approved["clip_id"]
            ):
                verified = VerifiedSpine42BundleReader(state_root).load(
                    approved["project_id"], outputs["skeleton_json_sha256"],
                    outputs["bundle_sha256"],
                )
                rebuilt = VerifiedSpine42Pipeline(state_root).rebuild_and_verify(
                    verified
                )
                self.assertEqual(approved, _projection(rebuilt))
                self.assertEqual(rebuilt.document_bytes, verified.document_bytes)
        self.assertEqual(before, _tree_snapshot(state_root))


if __name__ == "__main__":
    unittest.main()
