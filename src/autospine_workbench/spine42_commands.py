"""Safe services for exact-address Spine 4.2 export bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .spine42_bundle_contract import (
    Spine42BundleContractError, build_spine42_bundle_contract,
)
from .spine42_bundle_integrity import (
    Spine42BundleIntegrityError, VerifiedSpine42BundleReader,
)
from .spine42_bundle_store import (
    Spine42BundleStore, Spine42BundleStoreError,
)
from .spine42_pipeline import (
    VerifiedSpine42Pipeline, VerifiedSpine42PipelineError,
)


class Spine42CommandError(RuntimeError):
    """Raised when an exact P6 command cannot prove its result."""


@dataclass(frozen=True, slots=True)
class Spine42CommandResult:
    """Frozen public identity for one fully rebuilt Spine 4.2 bundle."""

    path: Path
    project_id: str
    mode: str
    clip_id: str | None
    skeleton_json_sha256: str
    atlas_sha256: str
    png_sha256: str
    run_identity_sha256: str
    run_document_sha256: str
    report_sha256: str
    bundle_sha256: str
    summary: str
    reused: bool | None
    _source_items: tuple[
        tuple[str, tuple[tuple[str, str], ...] | None], ...] = field(repr=False)

    @property
    def source_addresses(self) -> dict[str, Any]:
        return {
            name: None if items is None else dict(items)
            for name, items in self._source_items
        }

    @property
    def output_sha256s(self) -> dict[str, str]:
        return {
            "skeleton_json_sha256": self.skeleton_json_sha256,
            "atlas_sha256": self.atlas_sha256,
            "png_sha256": self.png_sha256,
            "run_identity_sha256": self.run_identity_sha256,
            "run_document_sha256": self.run_document_sha256,
            "report_sha256": self.report_sha256,
            "bundle_sha256": self.bundle_sha256,
        }


def compile_spine42_bundle(
    state_root: Path,
    project_id: str,
    *,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str | None = None,
    motion_bundle_sha256: str | None = None,
) -> Spine42CommandResult:
    """Compile, publish, read back, and exactly rebuild one P6 export."""

    try:
        _require_motion_pair(motion_instance_sha256, motion_bundle_sha256)
        pipeline = VerifiedSpine42Pipeline(state_root)
        compilation = pipeline.build(
            project_id, p3_rig_sha256, p3_bundle_sha256,
            motion_instance_sha256=motion_instance_sha256,
            motion_bundle_sha256=motion_bundle_sha256,
        )
        contract = build_spine42_bundle_contract(
            project_id,
            compilation.p3_source,
            compilation.skeleton_json,
            compilation.atlas_bytes,
            compilation.png_bytes,
            compilation.source_image_sha256s,
            p5_source=compilation.p5_source,
        )
        _require_compilation(compilation, contract, project_id,
                             p3_rig_sha256, p3_bundle_sha256,
                             motion_instance_sha256, motion_bundle_sha256)
        published = Spine42BundleStore(state_root).publish(
            project_id,
            compilation.p3_source,
            compilation.skeleton_json,
            compilation.atlas_bytes,
            compilation.png_bytes,
            compilation.source_image_sha256s,
            p5_source=compilation.p5_source,
        )
        _require_publication(published, contract)
        verified = VerifiedSpine42BundleReader(state_root).load(
            project_id, published.skeleton_json_sha256,
            published.bundle_sha256)
        rebuilt = pipeline.rebuild_and_verify(verified)
        if rebuilt != compilation:
            raise Spine42CommandError(
                "Spine readback rebuild differs from the compiled snapshot")
        return _result(verified, rebuilt, reused=published.reused,
                       expected_path=published.path)
    except Spine42CommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise Spine42CommandError(f"Spine 4.2 bundle compilation failed: {exc}") from exc


def verify_spine42_bundle(
    state_root: Path,
    project_id: str,
    *,
    skeleton_json_sha256: str,
    bundle_sha256: str,
) -> Spine42CommandResult:
    """Read and rebuild one explicit P6 address without writing state."""

    try:
        verified = VerifiedSpine42BundleReader(state_root).load(
            project_id, skeleton_json_sha256, bundle_sha256
        )
        rebuilt = VerifiedSpine42Pipeline(state_root).rebuild_and_verify(verified)
        return _result(verified, rebuilt, reused=None)
    except Spine42CommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise Spine42CommandError(f"Spine 4.2 bundle verification failed: {exc}") from exc


def _require_compilation(
    value: Any,
    contract: Any,
    project: str,
    p3_rig: str,
    p3_bundle: str,
    motion_instance: str | None,
    motion_bundle: str | None,
) -> None:
    expected_p5 = value.p5_source
    contract_p5 = json.loads(
        contract.document_bytes["run-manifest.json"]
    )["inputs"]["p5"]
    if motion_instance is None:
        requested_p5 = expected_p5 is None
    else:
        requested_p5 = (
            isinstance(expected_p5, Mapping)
            and expected_p5.get("motion_instance_sha256") == motion_instance
            and expected_p5.get("bundle_sha256") == motion_bundle
        )
    valid_mode = (
        value.mode == contract.mode
        and value.clip_id == contract.clip_id
        and expected_p5 == contract_p5
        and requested_p5
    )
    expected_identities = {
        "skeleton_json_sha256": contract.skeleton_json_sha256,
        "atlas_sha256": contract.atlas_sha256,
        "png_sha256": contract.png_sha256,
        "run_identity_sha256": contract.run_identity_sha256,
        "run_document_sha256": contract.run_document_sha256,
        "report_sha256": contract.report_sha256,
        "bundle_sha256": contract.bundle_sha256,
    }
    if (
        value.project_id != project
        or value.p3_source != {
            "rig_sha256": p3_rig,
            "bundle_sha256": p3_bundle,
        }
        or not valid_mode
        or value.contract_identities != expected_identities
        or value.document_bytes != contract.document_bytes
    ):
        raise Spine42CommandError("Spine pipeline identity or canonical contract differs")


def _require_publication(published: Any, contract: Any) -> None:
    expected = {
        "project_id": contract.project_id,
        "mode": contract.mode,
        "clip_id": contract.clip_id,
        "skeleton_json_sha256": contract.skeleton_json_sha256,
        "atlas_sha256": contract.atlas_sha256,
        "png_sha256": contract.png_sha256,
        "run_document_sha256": contract.run_document_sha256,
        "report_sha256": contract.report_sha256,
        "bundle_sha256": contract.bundle_sha256,
    }
    if any(getattr(published, name, None) != value
           for name, value in expected.items()):
        raise Spine42CommandError(
            "Published Spine identity differs from its contract")
    if not isinstance(getattr(published, "path", None), Path) \
            or type(getattr(published, "reused", None)) is not bool:
        raise Spine42CommandError(
            "Published Spine path or reuse status is invalid")


def _result(
    verified: Any,
    rebuilt: Any,
    *,
    reused: bool | None,
    expected_path: Path | None = None,
) -> Spine42CommandResult:
    fields = (
        "project_id", "mode", "clip_id", "skeleton_json_sha256",
        "atlas_sha256", "png_sha256", "run_identity_sha256",
        "run_document_sha256", "report_sha256", "bundle_sha256",
    )
    if verified.document_bytes != rebuilt.document_bytes or any(
        getattr(verified, name, None) != getattr(rebuilt, name, None)
        for name in fields
    ):
        raise Spine42CommandError(
            "Verified Spine bundle differs from its upstream rebuild")
    path = getattr(verified, "path", None)
    if not isinstance(path, Path) or expected_path is not None and (
        path.resolve(strict=True) != Path(expected_path).resolve(strict=True)
    ):
        raise Spine42CommandError(
            "Verified Spine path differs from publication")
    if reused is not None and type(reused) is not bool:
        raise Spine42CommandError("Verified Spine reuse status is invalid")
    sources = (
        ("p3", tuple(rebuilt.p3_source.items())),
        ("p5", None if rebuilt.p5_source is None
         else tuple(rebuilt.p5_source.items())),
    )
    metrics = verified.export_report.get("metrics")
    if type(metrics) is not dict or verified.export_report.get("status") != "passed":
        raise Spine42CommandError("Verified Spine report summary is invalid")
    summary = _summary(verified.mode, verified.clip_id, metrics)
    return Spine42CommandResult(
        path, verified.project_id, verified.mode, verified.clip_id,
        verified.skeleton_json_sha256, verified.atlas_sha256,
        verified.png_sha256, verified.run_identity_sha256,
        verified.run_document_sha256, verified.report_sha256,
        verified.bundle_sha256, summary, reused, sources)


def _summary(mode: str, clip_id: str | None, metrics: Mapping[str, Any]) -> str:
    fields = ("bones", "slots", "attachments", "animations", "events")
    if any(type(metrics.get(name)) is not int for name in fields) \
            or any(metrics[name] < 0 for name in fields):
        raise Spine42CommandError("Verified Spine metrics are invalid")
    clip = "none" if clip_id is None else clip_id
    counts = ";".join(f"{name}={metrics[name]}" for name in fields)
    return f"mode={mode};clip={clip};{counts}"


def _require_motion_pair(instance: str | None, bundle: str | None) -> None:
    if (instance is None) != (bundle is None):
        raise Spine42CommandError("Motion addresses must be supplied together")


_DOMAIN_ERRORS = (AttributeError, KeyError, OSError, OverflowError,
    Spine42BundleContractError, Spine42BundleIntegrityError,
    Spine42BundleStoreError, VerifiedSpine42PipelineError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)
