"""Pure bounded comparison of one P10 setup capture to one approved P6 image."""

from __future__ import annotations

from typing import Any

from .png_rgba import RgbaPngError, decode_rgba_png
from .rgba_regression_metrics import (
    RgbaRegressionMetricsError,
    compute_rgba_regression_metrics,
)
from .spine42_runtime_contract import require_runtime_golden
from .spine42_bundle_integrity import VerifiedSpine42Bundle
from .spine42_v3_bundle_integrity import VerifiedSpine42V3Bundle
from .spine42_v3_runtime_evidence import sha256
from .spine42_v3_runtime_reader import VerifiedSpine42V3RuntimeEvidence
from .spine42_v3_setup_regression_sample import (
    setup_regression_sample_sha256,
    threshold_reason_codes,
)
from .spine42_v3_setup_regression_sources import (
    bind_setup_regression_sources,
)


class Spine42V3SetupRegressionError(ValueError):
    """Raised when comparison inputs are invalid or cross-wired."""


def compare_spine42_v3_setup_sample(
    sample: dict[str, Any],
    p6_approval: dict[str, Any],
    runtime_golden: dict[str, Any],
    approved_png_bytes: bytes,
    p6_bundle: VerifiedSpine42Bundle,
    spine: VerifiedSpine42V3Bundle,
    runtime: VerifiedSpine42V3RuntimeEvidence,
) -> dict[str, Any]:
    """Replay both source chains and produce one path-free sample result."""

    try:
        p6, golden, plan, artifact, report = bind_setup_regression_sources(
            sample, p6_approval, runtime_golden, p6_bundle, spine, runtime,
        )
        approved, actual = _images(
            runtime_golden, golden, approved_png_bytes,
            runtime.evidence.capture_bytes[artifact["artifact_id"]],
        )
        metrics = compute_rgba_regression_metrics(actual, approved)
        thresholds = golden["thresholds"]
        reasons = threshold_reason_codes(metrics, thresholds)
        result = {
            "project_id": sample["project_id"],
            "source": {
                "p3_rig_sha256": spine.p3_rig_sha256,
                "p3_bundle_sha256": spine.p3_bundle_sha256,
                "p6_skeleton_json_sha256": p6["outputs"]["skeleton_json_sha256"],
                "p6_bundle_sha256": p6["outputs"]["bundle_sha256"],
                "spine42_v3_skeleton_json_sha256": spine.skeleton_json_sha256,
                "spine42_v3_bundle_sha256": spine.bundle_sha256,
                "runtime_capture_bundle_sha256": runtime.capture_bundle_sha256,
                "capture_plan_sha256": plan["capture_plan_sha256"],
                "spine42_v3_run_document_sha256": spine.run_document_sha256,
                "raster_metrics_sha256":
                    runtime.evidence.manifest["source"]["raster_metrics_sha256"],
                "runtime_session_set_sha256":
                    runtime.evidence.manifest["source"]["runtime_session_set_sha256"],
                "runtime_capture_manifest_sha256":
                    sha256(runtime.evidence.manifest_bytes),
            },
            "actual": {
                "artifact_id": artifact["artifact_id"],
                "case_id": "setup",
                "kind": "opaque_composite",
                "animation": None,
                "tick": 0,
                "png_sha256": report["image"]["png_sha256"],
                "rgba_sha256": sha256(actual.pixels),
                "width": actual.width,
                "height": actual.height,
            },
            "approved": {
                "runtime_case_id": golden["id"],
                "png_sha256": golden["golden"]["png_sha256"],
                "rgba_sha256": sha256(approved.pixels),
                "width": approved.width,
                "height": approved.height,
            },
            "metrics": metrics,
            "thresholds": thresholds,
            "reason_codes": reasons,
            "status": "passed" if not reasons else "rejected",
        }
        result["comparison_sha256"] = setup_regression_sample_sha256(result)
        return result
    except Spine42V3SetupRegressionError:
        raise
    except (
        AttributeError, KeyError, RgbaPngError, RgbaRegressionMetricsError,
        RuntimeError, TypeError, ValueError,
    ) as exc:
        raise Spine42V3SetupRegressionError(
            "Spine v3 setup comparison failed"
        ) from exc


def _images(runtime_golden, golden, approved_bytes, actual_bytes):
    if type(approved_bytes) is not bytes or type(actual_bytes) is not bytes \
            or sha256(approved_bytes) != golden["golden"]["png_sha256"]:
        raise Spine42V3SetupRegressionError("Approved PNG bytes changed")
    approved = decode_rgba_png(approved_bytes, source_name="approved setup PNG")
    actual = decode_rgba_png(actual_bytes, source_name="captured setup PNG")
    capture = require_runtime_golden(runtime_golden)["capture"]
    size = capture["viewport"]
    dpr = capture["device_pixel_ratio"]
    expected = (size["width"] * dpr, size["height"] * dpr)
    if (approved.width, approved.height) != expected \
            or (actual.width, actual.height) != expected:
        raise Spine42V3SetupRegressionError("Setup PNG dimensions differ")
    return approved, actual


__all__ = [
    "Spine42V3SetupRegressionError", "compare_spine42_v3_setup_sample",
]
