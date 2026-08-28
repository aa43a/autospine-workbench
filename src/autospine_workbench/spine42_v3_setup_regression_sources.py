"""Exact source-chain binding for one P10.7c setup comparison."""

from __future__ import annotations

from .p6_spine42_approval import approved_p6_setup_case
from .spine42_runtime_contract import require_runtime_golden
from .spine42_bundle_integrity import (
    VerifiedSpine42Bundle,
    replay_verified_spine42_bundle,
)
from .spine42_v3_bundle_integrity import (
    VerifiedSpine42V3Bundle,
    replay_verified_spine42_v3_bundle,
)
from .spine42_v3_runtime_plan import (
    build_spine42_v3_runtime_plan,
    canonical_spine42_v3_runtime_plan_bytes,
)
from .spine42_v3_runtime_bundle import build_spine42_v3_runtime_bundle
from .spine42_v3_runtime_reader import VerifiedSpine42V3RuntimeEvidence


class Spine42V3SetupRegressionSourceError(ValueError):
    """Raised when exact comparison sources are invalid or cross-wired."""


def bind_setup_regression_sources(
    sample, p6_approval, runtime_golden, p6_bundle, spine, runtime,
):
    """Replay and bind P6, P10.7a, P10.7b, and approved-golden sources."""

    if type(p6_bundle) is not VerifiedSpine42Bundle \
            or type(spine) is not VerifiedSpine42V3Bundle \
            or type(runtime) is not VerifiedSpine42V3RuntimeEvidence:
        raise Spine42V3SetupRegressionSourceError(
            "Setup comparison requires exact verified inputs"
        )
    replay_verified_spine42_bundle(p6_bundle)
    replay_verified_spine42_v3_bundle(spine)
    if build_spine42_v3_runtime_bundle(runtime.evidence) != runtime.bundle:
        raise Spine42V3SetupRegressionSourceError(
            "Runtime capture wrapper differs from exact evidence replay"
        )
    _bind_addresses(sample, spine, runtime)
    p6 = approved_p6_setup_case(
        p6_approval, sample["project_id"],
        sample["p6_setup_address"]["skeleton_json_sha256"],
        sample["p6_setup_address"]["bundle_sha256"],
    )
    _bind_p3_and_assets(sample, p6, p6_bundle, spine)
    golden = _golden_case(runtime_golden, sample, p6)
    plan = _exact_runtime_plan(spine, runtime)
    artifact, report = _setup_opaque_artifact(runtime, plan, spine)
    _bind_profiles(runtime_golden, plan, artifact)
    return p6, golden, plan, artifact, report


def _bind_addresses(sample, spine, runtime) -> None:
    spine_address = sample["spine42_v3_address"]
    capture_address = sample["runtime_capture_address"]
    actual = (
        spine.project_id, spine.skeleton_json_sha256, spine.bundle_sha256,
        runtime.project_id, runtime.spine42_v3_bundle_sha256,
        runtime.capture_bundle_sha256,
    )
    expected = (
        sample["project_id"], spine_address["skeleton_json_sha256"],
        spine_address["bundle_sha256"], sample["project_id"],
        capture_address["spine42_v3_bundle_sha256"],
        capture_address["capture_bundle_sha256"],
    )
    if actual != expected:
        raise Spine42V3SetupRegressionSourceError(
            "Setup comparison exact addresses are cross-wired"
        )


def _bind_p3_and_assets(sample, p6, exact, spine) -> None:
    outputs = p6["outputs"]
    exact_outputs = (
        exact.skeleton_json_sha256, exact.atlas_sha256, exact.png_sha256,
        exact.run_identity_sha256, exact.run_document_sha256,
        exact.report_sha256, exact.bundle_sha256,
    )
    approved_outputs = tuple(outputs[field] for field in (
        "skeleton_json_sha256", "atlas_sha256", "png_sha256",
        "run_identity_sha256", "run_document_sha256", "report_sha256",
        "bundle_sha256",
    ))
    inputs = exact.run_manifest["inputs"]
    if exact.project_id != p6["project_id"] or exact.mode != "setup-only" \
            or exact.clip_id is not None or exact_outputs != approved_outputs \
            or inputs["p5"] is not None \
            or inputs["p3"] != {
                "rig_sha256": p6["request"]["p3_rig_sha256"],
                "bundle_sha256": p6["request"]["p3_bundle_sha256"],
            }:
        raise Spine42V3SetupRegressionSourceError(
            "Exact P6 setup bundle differs from its approval"
        )
    if (
        sample["p3_rig_sha256"], sample["p3_bundle_sha256"],
        p6["request"]["p3_rig_sha256"],
        p6["request"]["p3_bundle_sha256"],
        outputs["atlas_sha256"], outputs["png_sha256"],
    ) != (
        spine.p3_rig_sha256, spine.p3_bundle_sha256,
        spine.p3_rig_sha256, spine.p3_bundle_sha256,
        spine.atlas_sha256, spine.png_sha256,
    ):
        raise Spine42V3SetupRegressionSourceError(
            "P6 and Spine v3 setup sources are cross-wired"
        )


def _golden_case(runtime_golden, sample, p6):
    golden = require_runtime_golden(runtime_golden)
    rows = [
        row for row in golden["cases"]
        if row["id"] == sample["approved_runtime_case_id"]
    ]
    if len(rows) != 1:
        raise Spine42V3SetupRegressionSourceError(
            "Approved runtime case is missing or ambiguous"
        )
    row = rows[0]
    assets = p6["outputs"]
    if row["clip"] is not None or row["time_seconds"] != 0.0 \
            or row["golden"]["png_sha256"] != sample["approved_png_sha256"] \
            or row["assets"] != {
                "skeleton_sha256": assets["skeleton_json_sha256"],
                "atlas_sha256": assets["atlas_sha256"],
                "texture_sha256": assets["png_sha256"],
            }:
        raise Spine42V3SetupRegressionSourceError(
            "Approved runtime setup case is cross-wired"
        )
    matches = [
        item for item in golden["cases"]
        if item["clip"] is None
        and item["assets"]["atlas_sha256"] == assets["atlas_sha256"]
        and item["assets"]["texture_sha256"] == assets["png_sha256"]
    ]
    if len(matches) != 1:
        raise Spine42V3SetupRegressionSourceError(
            "Approved runtime setup identity is ambiguous"
        )
    return row


def _exact_runtime_plan(spine, runtime):
    plan = runtime.evidence.manifest["plan"]
    expected = build_spine42_v3_runtime_plan(spine)
    if canonical_spine42_v3_runtime_plan_bytes(plan) != \
            canonical_spine42_v3_runtime_plan_bytes(expected):
        raise Spine42V3SetupRegressionSourceError(
            "Runtime capture plan differs from the exact Spine v3 bundle"
        )
    source = runtime.evidence.manifest["source"]
    if source["skeleton_json_sha256"] != spine.skeleton_json_sha256 \
            or source["spine42_v3_bundle_sha256"] != spine.bundle_sha256 \
            or source["run_document_sha256"] != spine.run_document_sha256:
        raise Spine42V3SetupRegressionSourceError(
            "Runtime capture source differs from the exact Spine v3 bundle"
        )
    return plan


def _setup_opaque_artifact(runtime, plan, spine):
    cases = [
        row for row in plan["cases"]
        if row["case_id"] == "setup" and row["animation"] is None
        and row["tick"] == 0 and row["time_seconds"] == 0.0
    ]
    artifacts = [
        row for row in plan["artifacts"]
        if row["case_id"] == "setup" and row["kind"] == "opaque_composite"
    ]
    if len(cases) != 1 or len(artifacts) != 1 \
            or artifacts[0]["artifact_id"] not in cases[0]["artifact_ids"]:
        raise Spine42V3SetupRegressionSourceError(
            "Runtime capture has no unique opaque setup artifact"
        )
    reports = [
        row for row in runtime.evidence.manifest["reports"]
        if row["artifact"]["artifact_id"] == artifacts[0]["artifact_id"]
    ]
    if len(reports) != 1 or reports[0].get("assets") != {
        "skeleton_sha256": spine.skeleton_json_sha256,
        "atlas_sha256": spine.atlas_sha256,
        "texture_sha256": spine.png_sha256,
    }:
        raise Spine42V3SetupRegressionSourceError(
            "Runtime capture setup report is missing or cross-wired"
        )
    return artifacts[0], reports[0]


def _bind_profiles(runtime_golden, plan, artifact) -> None:
    golden = require_runtime_golden(runtime_golden)
    runtime = plan["runtime"]
    if any(golden["runtime"][key] != runtime[key] for key in golden["runtime"]):
        raise Spine42V3SetupRegressionSourceError("Runtime golden version differs")
    capture = plan["capture"]
    expected = golden["capture"]
    actual = {
        "viewport": capture["viewport"],
        "device_pixel_ratio": capture["device_pixel_ratio"],
        "background": capture["opaque_background"],
    }
    if actual != expected or artifact["background"] != expected["background"]:
        raise Spine42V3SetupRegressionSourceError("Runtime capture profile differs")


__all__ = [
    "Spine42V3SetupRegressionSourceError", "bind_setup_regression_sources",
]
