"""Application commands for exact P10.7a v2 Spine bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .manifest_artifacts import require_sha256
from .motion_instance_v3_bundle_reader_v2 import (
    VerifiedMotionInstanceV3BundleV2,
)
from .project_store import ProjectStore
from .seam_anchor_review_json import canonical_json_bytes
from .spine42_v3_bundle_files_v2 import NAMESPACE
from .spine42_v3_bundle_reader_v2 import (
    VerifiedSpine42V3BundleReaderV2,
    VerifiedSpine42V3BundleV2,
)
from .spine42_v3_bundle_store_v2 import (
    PublishedSpine42V3BundleV2,
    Spine42V3BundleStoreV2,
)
from .spine42_v3_current_heads_v2 import (
    load_motion_instance_v3_v2_and_dynamic_source,
    observe_spine42_v3_current_heads_v2,
)
from .spine42_v3_pipeline_result_v2 import VerifiedSpine42V3CompilationV2


class P10Spine42V3CommandV2Error(RuntimeError):
    """Fixed, path-free P10.7a v2 application failure boundary."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3CommandResultV2:
    mode: str
    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    bundle_sha256: str
    run_document_sha256: str
    report_sha256: str
    inventory: tuple[str, ...]
    reused: bool | None
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


def compile_body_sway_spine42_v3_v2_command(
    capture_job_reader,
    project_store: ProjectStore,
    project_id: str,
    *,
    motion_instance_v3_sha256: str,
    motion_instance_v3_bundle_sha256: str,
) -> P10Spine42V3CommandResultV2:
    """Compile and atomically publish under one stable v2 source closure."""

    try:
        primary = require_sha256(
            motion_instance_v3_sha256, "P10.6b v2 MotionInstance v3"
        )
        bundle = require_sha256(
            motion_instance_v3_bundle_sha256,
            "P10.6b v2 MotionInstance v3 bundle",
        )
        motion, source = load_motion_instance_v3_v2_and_dynamic_source(
            project_store.state_root, project_id, primary, bundle,
        )
        return _compile_verified(
            capture_job_reader, project_store, motion, source,
        )
    except _COMMAND_FAILURES as exc:
        raise P10Spine42V3CommandV2Error(
            "Body-sway Spine 4.2 v3 v2 compilation failed"
        ) from exc


def compile_verified_body_sway_spine42_v3_v2_command(
    capture_job_reader,
    project_store: ProjectStore,
    motion: VerifiedMotionInstanceV3BundleV2,
) -> P10Spine42V3CommandResultV2:
    """Compile one reader-issued source without replaying P10.6b again."""

    try:
        if type(motion) is not VerifiedMotionInstanceV3BundleV2:
            raise TypeError("Reader-issued P10.6b v2 source required")
        source = motion.document(
            "body-sway-motion-consumer-admission-v2.json"
        )["source"]["body_sway_dynamic_seam_probe_v2"]["source"]
        if type(source) is not dict:
            raise TypeError("P10.6b v2 dynamic source is invalid")
        return _compile_verified(
            capture_job_reader, project_store, motion, source,
        )
    except _COMMAND_FAILURES as exc:
        raise P10Spine42V3CommandV2Error(
            "Body-sway Spine 4.2 v3 v2 verified compilation failed"
        ) from exc


def _compile_verified(capture, store, motion, source):
    before = observe_spine42_v3_current_heads_v2(capture, store, source)
    from .spine42_v3_pipeline_v2 import VerifiedSpine42V3PipelineV2
    pending = VerifiedSpine42V3PipelineV2(
        store.state_root
    ).build_from_verified(motion)
    _require_motion_source(pending, motion)
    published = Spine42V3BundleStoreV2(capture, store).publish(
        pending, motion, before,
    )
    verified = published.verified_bundle
    _require_published(published, pending)
    _require_exact_readback(verified, pending)
    return _result(
        "compiled", verified, published.reused,
        head_check={
            "scope": "prepublication_compile_and_exact_readback",
            "before_after_identity": "exact_match",
            "before_after_canonical_bytes": "exact_match",
            "current_heads_observed": True,
            "permanent_authority_claimed": False,
        },
    )


def verify_body_sway_spine42_v3_v2_command(
    state_root: Path,
    project_id: str,
    *,
    skeleton_json_sha256: str,
    bundle_sha256: str,
) -> P10Spine42V3CommandResultV2:
    """Replay an immutable historical address without current-head reads."""

    try:
        skeleton = require_sha256(
            skeleton_json_sha256, "P10.7a v2 skeleton"
        )
        bundle = require_sha256(bundle_sha256, "P10.7a v2 bundle")
        verified = VerifiedSpine42V3BundleReaderV2(Path(state_root)).load(
            project_id, skeleton, bundle,
        )
        if verified.project_id != project_id \
                or verified.skeleton_json_sha256 != skeleton \
                or verified.bundle_sha256 != bundle:
            raise ValueError("P10.7a v2 historical address differs")
        return _result(
            "verified", verified, None,
            head_check={
                "scope": "historical_replay",
                "current_heads_observed": False,
                "permanent_authority_claimed": False,
            },
        )
    except _COMMAND_FAILURES as exc:
        raise P10Spine42V3CommandV2Error(
            "Body-sway Spine 4.2 v3 v2 verification failed"
        ) from exc


def _require_motion_source(compilation, motion) -> None:
    if type(compilation) is not VerifiedSpine42V3CompilationV2 \
            or compilation.project_id != motion.project_id \
            or compilation.clip_id != motion.clip_id \
            or compilation.motion_instance_v3_source != motion.identities:
        raise ValueError("P10.7a v2 compilation source differs")


def _require_published(published, expected) -> None:
    if type(published) is not PublishedSpine42V3BundleV2 \
            or published.project_id != expected.project_id \
            or published.clip_id != expected.clip_id \
            or published.skeleton_json_sha256 \
                != expected.skeleton_json_sha256 \
            or published.bundle_sha256 != expected.bundle_sha256 \
            or published.run_document_sha256 \
                != expected.run_document_sha256 \
            or published.report_sha256 != expected.report_sha256 \
            or type(published.reused) is not bool:
        raise ValueError("P10.7a v2 store postcondition failed")
    suffix = (
        published.path.name, published.path.parent.name,
        published.path.parent.parent.name,
        published.path.parent.parent.parent.name,
        published.path.parent.parent.parent.parent.name,
    )
    if suffix != (
        expected.bundle_sha256, expected.skeleton_json_sha256,
        NAMESPACE, expected.project_id, "builds",
    ):
        raise ValueError("P10.7a v2 store path postcondition failed")


def _require_exact_readback(verified, expected) -> None:
    if type(verified) is not VerifiedSpine42V3BundleV2 \
            or verified.project_id != expected.project_id \
            or verified.clip_id != expected.clip_id \
            or verified.contract_identities != expected.contract_identities \
            or verified.source_image_sha256s != expected.source_image_sha256s \
            or verified.document_bytes != expected.document_bytes:
        raise ValueError("P10.7a v2 exact readback failed")


def _result(mode, verified, reused, *, head_check):
    run = verified.run_manifest
    document = {
        "project_id": verified.project_id,
        "clip_id": verified.clip_id,
        "source": {
            "p3": verified.p3_source,
            "motion_instance_v3_v2": verified.motion_instance_v3_source,
        },
        "address": {
            "skeleton_json_sha256": verified.skeleton_json_sha256,
            "bundle_sha256": verified.bundle_sha256,
        },
        "outputs": {
            name: getattr(verified, name) for name in (
                "atlas_sha256", "png_sha256", "run_identity_sha256",
                "run_document_sha256", "report_sha256",
            )
        },
        "inventory": list(verified.inventory),
        "authority": run["authority"],
        "release_gate": run["release_gate"],
        "reused": reused,
        "head_check": head_check,
        "verification": {"status": "passed", "exact_readback": True},
    }
    return P10Spine42V3CommandResultV2(
        mode, verified.project_id, verified.clip_id,
        verified.skeleton_json_sha256, verified.bundle_sha256,
        verified.run_document_sha256, verified.report_sha256,
        verified.inventory, reused,
        canonical_json_bytes(document).decode("utf-8"),
    )


_COMMAND_FAILURES = (
    AttributeError, KeyError, OSError, OverflowError, RecursionError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "P10Spine42V3CommandResultV2", "P10Spine42V3CommandV2Error",
    "compile_body_sway_spine42_v3_v2_command",
    "compile_verified_body_sway_spine42_v3_v2_command",
    "verify_body_sway_spine42_v3_v2_command",
]
