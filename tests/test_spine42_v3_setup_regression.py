"""P10.7c exact setup regression contracts, comparison, and command tests."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_spine42_v3_setup_regression_commands import (  # noqa: E402
    P10Spine42V3SetupRegressionCommandError,
    compare_body_sway_spine42_v3_setup_command,
)
from autospine_workbench.p6_spine42_approval import (  # noqa: E402
    P6Spine42ApprovalError,
    require_p6_spine42_approval,
)
from autospine_workbench.png_rgba import (  # noqa: E402
    RgbaImage,
    decode_rgba_png,
    encode_rgba_png,
)
from autospine_workbench.spine42_runtime_contract import (  # noqa: E402
    RUNTIME_NPM_INTEGRITY,
)
from autospine_workbench.spine42_bundle_integrity import (  # noqa: E402
    VerifiedSpine42Bundle,
)
from autospine_workbench.spine42_v3_bundle_integrity import (  # noqa: E402
    VerifiedSpine42V3Bundle,
)
from autospine_workbench.spine42_v3_runtime_bundle import (  # noqa: E402
    build_spine42_v3_runtime_bundle,
)
from autospine_workbench.spine42_v3_runtime_evidence import (  # noqa: E402
    Spine42V3RuntimeEvidence,
)
from autospine_workbench.spine42_v3_runtime_reader import (  # noqa: E402
    VerifiedSpine42V3RuntimeEvidence,
)
from autospine_workbench.spine42_v3_setup_regression_comparison import (  # noqa: E402
    Spine42V3SetupRegressionError,
    compare_spine42_v3_setup_sample,
)
from autospine_workbench.spine42_v3_setup_regression_manifest import (  # noqa: E402
    Spine42V3SetupRegressionManifestError,
    canonical_request_bytes,
    parse_spine42_v3_setup_regression_request,
    require_spine42_v3_setup_regression_request,
)
from autospine_workbench.spine42_v3_setup_regression_profile import (  # noqa: E402
    COMPARISON_PROFILE_SHA256,
)
from autospine_workbench.spine42_v3_setup_regression_report import (  # noqa: E402
    Spine42V3SetupRegressionReportError,
    build_spine42_v3_setup_regression_report,
    require_spine42_v3_setup_regression_report,
)
from tests.test_spine42_v3_runtime_evidence_store import (  # noqa: E402
    CLIP,
    PROJECT,
    RUN_SHA,
    SKELETON_SHA,
    UPSTREAM_SHA,
    _evidence,
    _plan,
)


P3_RIG, P3_BUNDLE = "a" * 64, "b" * 64
P6_SKELETON, P6_BUNDLE = "c" * 64, "d" * 64
ATLAS, TEXTURE = "5" * 64, "6" * 64
P6_CASE = "fixture.setup"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def opaque_png() -> bytes:
    return _evidence().capture_bytes["case-000.opaque"]


def p6_approval() -> dict:
    return {
        "format": "autospine-p6-spine42-golden", "format_version": 1,
        "cases": [{
            "project_id": PROJECT, "mode": "setup-only", "clip_id": None,
            "request": {
                "p3_rig_sha256": P3_RIG, "p3_bundle_sha256": P3_BUNDLE,
                "motion_instance_sha256": None, "motion_bundle_sha256": None,
            },
            "outputs": {
                "skeleton_json_sha256": P6_SKELETON,
                "atlas_sha256": ATLAS, "png_sha256": TEXTURE,
                "run_identity_sha256": "e" * 64,
                "run_document_sha256": "f" * 64,
                "report_sha256": "0" * 64, "bundle_sha256": P6_BUNDLE,
            },
            "gate": {
                "status": "passed", "summary": "fixture",
                "checks": {
                    "adapter-profile": "passed",
                    "attachment-atlas-binding": "passed",
                    "atlas-png-geometry": "passed",
                    "source-image-binding": "passed",
                    "motion-binding": "not_applicable",
                },
                "metrics": {
                    "bones": 1, "slots": 1, "attachments": 1,
                    "animations": 0, "events": 0, "atlas_regions": 1,
                    "atlas_width": 640, "atlas_height": 640,
                    "source_images": 1,
                },
            },
        }],
    }


def runtime_golden(png_sha: str) -> dict:
    cases = []
    for case_id, clip, time in (
        (P6_CASE, None, 0.0), ("fixture.idle", "idle", 1.0),
        ("fixture.wave", "wave.left", 0.6),
    ):
        cases.append({
            "id": case_id, "clip": clip, "time_seconds": time,
            "assets": {
                "skeleton_sha256": P6_SKELETON,
                "atlas_sha256": ATLAS, "texture_sha256": TEXTURE,
            },
            "golden": {
                "path": f"{case_id}.approved.png", "png_sha256": png_sha,
            },
            "thresholds": {
                "max_differing_pixel_ratio": 0.0,
                "max_mean_absolute_error": 0.0,
                "max_channel_delta": 0,
            },
        })
    return {
        "format": "autospine-spine42-runtime-golden", "format_version": 1,
        "runtime": {
            "package": "@esotericsoftware/spine-player", "version": "4.2.119",
            "npm_integrity": RUNTIME_NPM_INTEGRITY,
        },
        "capture": {
            "viewport": {"width": 640, "height": 640},
            "device_pixel_ratio": 1, "background": "#20242aff",
        },
        "cases": cases,
    }


def request(p6_raw: bytes, golden_raw: bytes, png_sha: str) -> dict:
    return {
        "format": "autospine-spine42-v3-setup-regression-request",
        "format_version": 1,
        "approved_p6_export_contract_sha256": sha(p6_raw),
        "approved_runtime_golden_sha256": sha(golden_raw),
        "comparison_profile_sha256": COMPARISON_PROFILE_SHA256,
        "samples": [{
            "project_id": PROJECT,
            "p3_rig_sha256": P3_RIG,
            "p3_bundle_sha256": P3_BUNDLE,
            "p6_setup_address": {
                "skeleton_json_sha256": P6_SKELETON,
                "bundle_sha256": P6_BUNDLE,
            },
            "spine42_v3_address": {
                "skeleton_json_sha256": SKELETON_SHA,
                "bundle_sha256": UPSTREAM_SHA,
            },
            "runtime_capture_address": {
                "spine42_v3_bundle_sha256": UPSTREAM_SHA,
                "capture_bundle_sha256": build_spine42_v3_runtime_bundle(
                    _evidence()
                ).bundle_sha256,
            },
            "approved_runtime_case_id": P6_CASE,
            "approved_png_sha256": png_sha,
        }],
    }


def verified_inputs():
    evidence = _evidence()
    runtime = VerifiedSpine42V3RuntimeEvidence(
        Path("unused"), evidence, build_spine42_v3_runtime_bundle(evidence)
    )
    spine = VerifiedSpine42V3Bundle(
        Path("unused"), PROJECT, CLIP, "1" * 64, P3_RIG, P3_BUNDLE,
        "2" * 64, "3" * 64, "4" * 64, "7" * 64, "8" * 64,
        SKELETON_SHA, ATLAS, TEXTURE, "9" * 64, RUN_SHA, "0" * 64,
        UPSTREAM_SHA, (), (),
    )
    p6 = VerifiedSpine42Bundle(
        Path("unused"), PROJECT, "setup-only", None,
        P6_SKELETON, ATLAS, TEXTURE, "e" * 64, "f" * 64, "0" * 64,
        P6_BUNDLE,
        (("run-manifest.json", canonical({
            "inputs": {
                "p3": {"rig_sha256": P3_RIG, "bundle_sha256": P3_BUNDLE},
                "p5": None,
            },
        })),),
        (),
    )
    return p6, spine, runtime


def canonical(value: dict) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode()


@contextmanager
def patched_sources():
    with patch(
        "autospine_workbench.spine42_v3_setup_regression_sources."
        "replay_verified_spine42_bundle"
    ), patch(
        "autospine_workbench.spine42_v3_setup_regression_sources."
        "replay_verified_spine42_v3_bundle"
    ), patch(
        "autospine_workbench.spine42_v3_setup_regression_sources."
        "build_spine42_v3_runtime_plan", return_value=_plan(),
    ):
        yield


class Spine42V3SetupRegressionTests(unittest.TestCase):
    def inputs(self, approved=None):
        png = opaque_png() if approved is None else approved
        p6_raw = canonical(p6_approval())
        golden = runtime_golden(sha(png))
        golden_raw = canonical(golden)
        return png, p6_raw, golden_raw, request(p6_raw, golden_raw, sha(png)), golden

    def compare(self, approved=None):
        png, p6_raw, _golden_raw, req, golden = self.inputs(approved)
        p6_bundle, spine, runtime = verified_inputs()
        with patched_sources():
            row = compare_spine42_v3_setup_sample(
                req["samples"][0], json.loads(p6_raw), golden,
                png, p6_bundle, spine, runtime,
            )
        return req, row

    def test_exact_match_is_deterministic_and_self_hashed(self):
        req, row = self.compare()
        first = build_spine42_v3_setup_regression_report(req, [row])
        second = build_spine42_v3_setup_regression_report(req, [row])
        self.assertEqual(first, second)
        self.assertEqual("passed", first["status"])
        self.assertEqual(0, row["metrics"]["differing_pixels"])
        require_spine42_v3_setup_regression_report(first, req)
        tampered = deepcopy(first)
        tampered["authority"]["release"] = True
        with self.assertRaises(Spine42V3SetupRegressionReportError):
            require_spine42_v3_setup_regression_report(tampered, req)

    def test_one_pixel_change_is_a_valid_rejection(self):
        actual = decode_rgba_png(opaque_png())
        pixels = bytearray(actual.pixels)
        pixels[0] ^= 1
        req, row = self.compare(encode_rgba_png(RgbaImage(
            actual.width, actual.height, bytes(pixels)
        )))
        report = build_spine42_v3_setup_regression_report(req, [row])
        self.assertEqual("rejected", report["status"])
        self.assertEqual(1, row["metrics"]["differing_pixels"])
        self.assertEqual([
            "differing_pixel_ratio_exceeded",
            "mean_absolute_error_exceeded",
            "max_channel_delta_exceeded",
        ], row["reason_codes"])

    def test_request_and_approval_fail_closed(self):
        png, p6_raw, golden_raw, req, _golden = self.inputs()
        exact = canonical_request_bytes(req)
        self.assertEqual(req, parse_spine42_v3_setup_regression_request(exact))
        with self.assertRaises(Spine42V3SetupRegressionManifestError):
            parse_spine42_v3_setup_regression_request(exact + b" ")
        cross = deepcopy(req)
        cross["samples"][0]["runtime_capture_address"][
            "spine42_v3_bundle_sha256"
        ] = "f" * 64
        with self.assertRaises(Spine42V3SetupRegressionManifestError):
            require_spine42_v3_setup_regression_request(cross)
        invalid = p6_approval()
        invalid["cases"][0]["gate"]["metrics"]["bones"] = True
        with self.assertRaises(P6Spine42ApprovalError):
            require_p6_spine42_approval(invalid)
        real = json.loads((
            ROOT / "tests" / "goldens" / "p6-spine42" /
            "real-exports.approved.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(6, len(require_p6_spine42_approval(real)["cases"]))
        self.assertTrue(png and p6_raw and golden_raw)

    def test_command_is_zero_write_and_contract_hashes_are_exact(self):
        png, p6_raw, golden_raw, req, _golden = self.inputs()
        p6_bundle, spine, runtime = verified_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "request.json"
            p6_path = root / "p6.json"
            golden_path = root / "runtime.json"
            manifest.write_bytes(canonical_request_bytes(req))
            p6_path.write_bytes(p6_raw)
            golden_path.write_bytes(golden_raw)
            (root / f"{P6_CASE}.approved.png").write_bytes(png)
            before = {path.name: sha(path.read_bytes()) for path in root.iterdir()}
            with patch(
                "autospine_workbench.p10_spine42_v3_setup_regression_commands."
                "VerifiedSpine42BundleReader.load", return_value=p6_bundle,
            ), patch(
                "autospine_workbench.p10_spine42_v3_setup_regression_commands."
                "VerifiedSpine42V3BundleReader.load", return_value=spine,
            ), patch(
                "autospine_workbench.p10_spine42_v3_setup_regression_commands."
                "VerifiedSpine42V3RuntimeReader.load", return_value=runtime,
            ), patched_sources():
                result = compare_body_sway_spine42_v3_setup_command(
                    root / "missing-state", manifest, p6_path, golden_path
                )
            after = {path.name: sha(path.read_bytes()) for path in root.iterdir()}
            self.assertEqual(before, after)
            self.assertFalse((root / "missing-state").exists())
            self.assertEqual("passed", result.status)
            p6_path.write_bytes(p6_raw + b" ")
            with self.assertRaises(P10Spine42V3SetupRegressionCommandError):
                compare_body_sway_spine42_v3_setup_command(
                    root, manifest, p6_path, golden_path
                )

    def test_wrong_runtime_case_or_source_is_rejected_as_input_error(self):
        png, p6_raw, _golden_raw, req, golden = self.inputs()
        p6_bundle, spine, runtime = verified_inputs()
        req["samples"][0]["approved_runtime_case_id"] = "fixture.idle"
        with patched_sources(), self.assertRaises(Spine42V3SetupRegressionError):
            compare_spine42_v3_setup_sample(
                req["samples"][0], json.loads(p6_raw), golden,
                png, p6_bundle, spine, runtime,
            )
        req["samples"][0]["approved_runtime_case_id"] = P6_CASE
        document = runtime.evidence.manifest
        document["reports"][0]["assets"]["atlas_sha256"] = "f" * 64
        evidence = runtime.evidence
        forged_runtime = VerifiedSpine42V3RuntimeEvidence(
            runtime.path,
            Spine42V3RuntimeEvidence(
                evidence.project_id, evidence.clip_id,
                evidence.spine42_v3_bundle_sha256,
                evidence.skeleton_json_sha256, evidence.run_document_sha256,
                evidence.capture_plan_sha256, evidence.raster_metrics_sha256,
                canonical(document), evidence.metrics_bytes,
                tuple(evidence.capture_bytes.items()),
            ),
            runtime.bundle,
        )
        with patched_sources(), self.assertRaises(Spine42V3SetupRegressionError):
            compare_spine42_v3_setup_sample(
                req["samples"][0], json.loads(p6_raw), golden,
                png, p6_bundle, spine, forged_runtime,
            )
        req["samples"][0]["p3_rig_sha256"] = "f" * 64
        with patched_sources(), self.assertRaises(Spine42V3SetupRegressionError):
            compare_spine42_v3_setup_sample(
                req["samples"][0], json.loads(p6_raw), golden,
                png, p6_bundle, spine, runtime,
            )


if __name__ == "__main__":
    unittest.main()
