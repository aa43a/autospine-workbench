"""Exact current-head service behind cached package-centric Preview v2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .body_sway_derived_cache import (
    BodySwayDerivedCacheError, body_sway_derived_cache_key,
    process_body_sway_derived_cache,
)
from .body_sway_preview_inputs_v2 import (
    BodySwayPreviewInputV2Error, require_body_sway_preview_inputs_v2,
)
from .body_sway_probe_application import _compile_derived
from .body_sway_probe_inputs import (
    BodySwayProbeInputError, require_body_sway_probe_inputs,
)
from .capture_framing_candidate import (
    CaptureFramingCandidateError, compile_capture_framing_candidate,
)
from .capture_framing_verified_head import (
    CaptureFramingVerifiedHeadError, read_capture_framing_verified_head,
)
from .current_project_chain import (
    CurrentProjectChainError, rebuild_current_project_chains,
)
from .idle_behavior_review_head import (
    IdleBehaviorReviewHeadError, read_idle_behavior_review_head,
)
from .idle_behavior_review_packages import (
    IdleBehaviorReviewPackageError,
    require_current_idle_behavior_review_address,
)
from .idle_behavior_review_replay import (
    IdleBehaviorReviewReplayError, replay_idle_behavior_review_package,
)
from .p10_preview_v2_cache import (
    P10PreviewV2CacheError, P10PreviewV2CacheKey,
    P10PreviewV2CacheLocator, P10PreviewV2CacheRecord,
    process_p10_preview_v2_cache,
)
from .p10_preview_v2_result import (
    P10PreviewV2CommandError, preview_v2_command_result,
)
from .project_store import ProjectStore, ProjectStoreError
from .resolved_project import canonical_sha256
from .temporary_body_sway_preview_v2 import (
    TemporaryBodySwayPreviewV2Error,
    compile_temporary_body_sway_preview_v2,
    require_exact_temporary_body_sway_preview_v2,
)


@dataclass(frozen=True, slots=True)
class _Context:
    locator: P10PreviewV2CacheLocator
    project_ids: tuple[str, ...]
    chains: dict
    address: object
    evidence: object
    p10_head: object
    inventory_sha256: str


def compile_cached_body_sway_preview_v2(
    store: ProjectStore, package_id: str,
):
    """Compile once; every hit rechecks current mutable heads and inventory."""

    locator = _locator(store, package_id)
    cache = process_p10_preview_v2_cache()
    try:
        record = cache.get_or_compile(
            locator,
            lambda value: _validate_record(store, value),
            lambda: _compile_record(store, locator),
        )
        return record.result
    except P10PreviewV2CommandError:
        raise
    except _FAILURES as exc:
        raise P10PreviewV2CommandError(
            f"Package-centric Preview v2 compilation failed: {exc}"
        ) from exc


def _compile_record(store, locator):
    context = _load_context(store, locator)
    evidence, p10_head = context.evidence, context.p10_head
    inputs = require_body_sway_probe_inputs(
        evidence.manifest, evidence.candidates.document,
        p10_head.decision.document, evidence.mesh_bundle,
        evidence.retarget_bundle, evidence.reviewed_contract,
    )
    derived_key = body_sway_derived_cache_key(
        store.state_root, context.address,
        evidence.candidates.sha256, p10_head,
    )
    derived = process_body_sway_derived_cache().get_or_compile(
        derived_key,
        lambda: _compile_derived(inputs, p10_head, locator.package_id),
    )
    report = derived.canvas_adjustment.reviewed_report
    viewport = derived.dynamic_viewport
    if viewport is None:
        raise P10PreviewV2CommandError("Preview v2 has no dynamic viewport")
    candidate = derived.capture_framing or compile_capture_framing_candidate(
        inputs, report, viewport, p10_head, package_id=locator.package_id,
    )
    framing = read_capture_framing_verified_head(store.state_root, candidate)
    if framing.decision is None:
        raise P10PreviewV2CommandError(
            "The selected package has no approved CaptureFraming head"
        )
    preview_inputs = require_body_sway_preview_inputs_v2(
        inputs, report, candidate, framing.decision, framing.snapshot,
        state_root=store.state_root, package_id=locator.package_id,
    )
    preview = compile_temporary_body_sway_preview_v2(
        preview_inputs, evidence.mesh_bundle,
    )
    replay_sha = require_exact_temporary_body_sway_preview_v2(
        preview_inputs, evidence.mesh_bundle,
        preview.document, preview.artifact_bytes,
    )
    if replay_sha != preview.sha256:
        raise P10PreviewV2CommandError(
            "Preview v2 identity changed during exact replay"
        )
    result = preview_v2_command_result(store, locator.package_id, preview)
    record = P10PreviewV2CacheRecord(
        _key(context, candidate, framing), context.address,
        evidence.candidates, candidate, result,
    )
    if not _validate_record(store, record):
        raise P10PreviewV2CommandError(
            "The selected current package changed during compilation"
        )
    return record


def _load_context(store, locator):
    project_ids = tuple(store.discover_project_ids())
    chains = rebuild_current_project_chains(store, project_ids)
    address = require_current_idle_behavior_review_address(
        store.state_root, locator.package_id,
        project_ids=project_ids, current_project_chains=chains,
    )
    evidence = replay_idle_behavior_review_package(store.state_root, address)
    p10_head = read_idle_behavior_review_head(
        store.state_root, evidence.candidates.document,
    )
    if p10_head.decision is None:
        raise P10PreviewV2CommandError(
            "The selected package has no current P10.1 decision"
        )
    inventory = _inventory_sha(
        locator, project_ids, chains, address,
        evidence.candidates.sha256,
    )
    return _Context(
        locator, project_ids, chains, address, evidence, p10_head, inventory,
    )


def _validate_record(store, record):
    locator = record.key.locator
    project_ids = tuple(store.discover_project_ids())
    chains = rebuild_current_project_chains(store, project_ids)
    address = require_current_idle_behavior_review_address(
        store.state_root, locator.package_id,
        project_ids=project_ids, current_project_chains=chains,
    )
    p10 = read_idle_behavior_review_head(
        store.state_root, record.candidates.document,
    )
    framing = read_capture_framing_verified_head(
        store.state_root, record.framing_candidate,
    )
    return address == record.address \
        and _record_key(
            locator, project_ids, chains, address, record, p10, framing,
        ) == record.key


def _record_key(locator, project_ids, chains, address, record, p10, framing):
    return P10PreviewV2CacheKey(
        locator,
        _inventory_sha(
            locator, project_ids, chains, address, record.candidates.sha256,
        ),
        record.candidates.sha256, p10.decision_sha256, p10.current_revision,
        record.framing_candidate.sha256,
        framing.decision_sha256, framing.current_revision,
    )


def _key(context, candidate, framing):
    return P10PreviewV2CacheKey(
        context.locator, context.inventory_sha256,
        context.evidence.candidates.sha256,
        context.p10_head.decision_sha256,
        context.p10_head.current_revision,
        candidate.sha256, framing.decision_sha256, framing.current_revision,
    )


def _inventory_sha(locator, project_ids, chains, address, candidate_sha):
    return canonical_sha256({
        "domain": "autospine-p10-preview-v2-cache-inventory/v1",
        "locator": {
            "package_id": locator.package_id,
            "compiler_inventory_sha256": locator.compiler_inventory_sha256,
        },
        "project_ids": list(project_ids),
        "current_chains": [{
            "project_id": key,
            "resolved_project_sha256": chains[key].resolved_project_sha256,
            "layer_manifest_sha256": chains[key].layer_manifest_sha256,
            "input_identity_sha256": chains[key].input_identity_sha256,
        } for key in sorted(chains)],
        "address": address.public_document(),
        "p10_candidate_sha256": candidate_sha,
    })


def _locator(store, package_id):
    if type(store) is not ProjectStore or not isinstance(package_id, str):
        raise P10PreviewV2CommandError("Preview v2 requires a ProjectStore")
    try:
        state = str(Path(store.state_root).resolve(strict=True))
        workspace = str(Path(store.workspace_root).resolve(strict=True))
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise P10PreviewV2CommandError("Preview v2 roots are unavailable") from exc
    inventory = canonical_sha256({
        "domain": "autospine-p10-preview-v2-compiler-inventory/v1",
        "callables": [{
            "name": name,
            "process_object_id": id(globals()[name]),
        } for name in _COMPILER_NAMES],
    })
    return P10PreviewV2CacheLocator(state, workspace, package_id, inventory)


_COMPILER_NAMES = (
    "_compile_derived",
    "compile_capture_framing_candidate",
    "compile_temporary_body_sway_preview_v2",
    "require_exact_temporary_body_sway_preview_v2",
    "require_body_sway_preview_inputs_v2",
    "require_body_sway_probe_inputs",
)

_FAILURES = (
    BodySwayDerivedCacheError, BodySwayPreviewInputV2Error,
    BodySwayProbeInputError, CaptureFramingCandidateError,
    CaptureFramingVerifiedHeadError, CurrentProjectChainError,
    IdleBehaviorReviewHeadError, IdleBehaviorReviewPackageError,
    IdleBehaviorReviewReplayError, OSError, OverflowError,
    P10PreviewV2CacheError, ProjectStoreError,
    TemporaryBodySwayPreviewV2Error, TypeError, UnicodeError, ValueError,
)
