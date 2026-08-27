"""Application commands for P10.7b runtime evidence publication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .spine42_v3_bundle_reader import (
    VerifiedSpine42V3BundleReader,
    VerifiedSpine42V3BundleReaderError,
)
from .spine42_v3_runtime_evidence import (
    Spine42V3RuntimeEvidenceError,
    build_spine42_v3_runtime_evidence,
)
from .spine42_v3_runtime_reader import (
    VerifiedSpine42V3RuntimeEvidence,
    VerifiedSpine42V3RuntimeReader,
    Spine42V3RuntimeReaderError,
)
from .spine42_v3_runtime_runner import (
    Spine42V3RuntimeRunnerError,
    run_spine42_v3_runtime_capture,
)
from .spine42_v3_runtime_store import (
    PublishedSpine42V3RuntimeEvidence,
    Spine42V3RuntimeStore,
    Spine42V3RuntimeStoreError,
)


class P10Spine42V3RuntimeCommandError(RuntimeError):
    """Fixed path-free failure boundary for P10.7b commands."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3RuntimeCommandResult:
    mode: str
    path: Path
    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    spine42_v3_bundle_sha256: str
    capture_plan_sha256: str
    raster_metrics_sha256: str
    manifest_sha256: str
    capture_bundle_sha256: str
    browser_family: str
    browser_reported_version: str
    case_count: int
    attachment_count: int
    artifact_count: int
    metrics_status: str
    release_gate_status: str
    reused: bool | None


def capture_body_sway_spine42_v3_runtime_command(
    state_root: Path,
    project_id: str,
    *,
    skeleton_json_sha256: str,
    spine42_v3_bundle_sha256: str,
    runtime_root: Path,
    browser_executable: Path,
    license_acknowledged: bool,
) -> P10Spine42V3RuntimeCommandResult:
    """Run, seal, publish, and read back one complete exact capture."""

    try:
        run = run_spine42_v3_runtime_capture(
            state_root, project_id,
            skeleton_json_sha256=skeleton_json_sha256,
            spine42_v3_bundle_sha256=spine42_v3_bundle_sha256,
            runtime_root=runtime_root,
            browser_executable=browser_executable,
            license_acknowledged=license_acknowledged,
        )
        bundle, runtime, browser, _sessions, snapshot = run.exact_inputs
        evidence = build_spine42_v3_runtime_evidence(
            bundle, runtime, browser, run.plan, snapshot, run.metrics,
            license_acknowledged=True,
        )
        published = Spine42V3RuntimeStore(state_root).publish(evidence)
        verified = VerifiedSpine42V3RuntimeReader(state_root).load(
            project_id, spine42_v3_bundle_sha256,
            published.capture_bundle_sha256,
        )
        _require_publication(published, verified, evidence)
        return _result("captured", verified, published.reused)
    except P10Spine42V3RuntimeCommandError:
        raise
    except _FAILURES as exc:
        raise P10Spine42V3RuntimeCommandError(
            "Body-sway Spine 4.2 v3 runtime capture failed"
        ) from exc


def verify_body_sway_spine42_v3_runtime_command(
    state_root: Path,
    project_id: str,
    *,
    spine42_v3_bundle_sha256: str,
    capture_bundle_sha256: str,
) -> P10Spine42V3RuntimeCommandResult:
    """Replay one stored capture plus its exact P10.7a source closure."""

    try:
        verified = VerifiedSpine42V3RuntimeReader(state_root).load(
            project_id, spine42_v3_bundle_sha256,
            capture_bundle_sha256,
        )
        manifest = verified.evidence.manifest
        source = manifest["source"]
        upstream = VerifiedSpine42V3BundleReader(state_root).load(
            project_id, source["skeleton_json_sha256"],
            spine42_v3_bundle_sha256,
        )
        if upstream.bundle_sha256 != verified.spine42_v3_bundle_sha256 \
                or upstream.run_document_sha256 \
                != source["run_document_sha256"]:
            raise P10Spine42V3RuntimeCommandError(
                "Runtime evidence differs from exact P10.7a replay"
            )
        return _result("verified", verified, None)
    except P10Spine42V3RuntimeCommandError:
        raise
    except _FAILURES as exc:
        raise P10Spine42V3RuntimeCommandError(
            "Body-sway Spine 4.2 v3 runtime verification failed"
        ) from exc


def _require_publication(published, verified, expected) -> None:
    if type(published) is not PublishedSpine42V3RuntimeEvidence \
            or type(verified) is not VerifiedSpine42V3RuntimeEvidence \
            or verified.evidence.manifest_bytes != expected.manifest_bytes \
            or verified.evidence.metrics_bytes != expected.metrics_bytes \
            or verified.evidence.capture_bytes != expected.capture_bytes \
            or verified.capture_bundle_sha256 \
            != published.capture_bundle_sha256:
        raise P10Spine42V3RuntimeCommandError(
            "Runtime evidence publication failed exact readback"
        )


def _result(mode, verified, reused):
    evidence, manifest = verified.evidence, verified.evidence.manifest
    metrics = evidence.metrics
    return P10Spine42V3RuntimeCommandResult(
        mode, verified.path, verified.project_id, evidence.clip_id,
        evidence.skeleton_json_sha256, evidence.spine42_v3_bundle_sha256,
        evidence.capture_plan_sha256, evidence.raster_metrics_sha256,
        verified.bundle.manifest_sha256, verified.capture_bundle_sha256,
        manifest["browser"]["family"],
        manifest["browser"]["reported_version"],
        len(manifest["plan"]["cases"]),
        len(manifest["plan"]["attachments"]),
        len(manifest["artifacts"]),
        "passed" if metrics["summary"]["all_sampled_cases_passed"]
            else "rejected",
        manifest["release_gate"]["status"], reused,
    )


_FAILURES = (
    AttributeError, KeyError, OSError, RuntimeError,
    Spine42V3RuntimeEvidenceError, Spine42V3RuntimeReaderError,
    Spine42V3RuntimeRunnerError, Spine42V3RuntimeStoreError,
    TypeError, ValueError, VerifiedSpine42V3BundleReaderError,
)


__all__ = [
    "P10Spine42V3RuntimeCommandError",
    "P10Spine42V3RuntimeCommandResult",
    "capture_body_sway_spine42_v3_runtime_command",
    "verify_body_sway_spine42_v3_runtime_command",
]
