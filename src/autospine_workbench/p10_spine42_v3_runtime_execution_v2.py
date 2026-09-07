"""Single-attempt execution of an authorized P10.7b v2 runtime job."""

from __future__ import annotations

from dataclasses import dataclass, field

from .p10_spine42_v3_runtime_authority_v2 import (
    P10Spine42V3RuntimeAuthorityV2,
    P10Spine42V3RuntimeAuthorityV2Error,
)
from .p10_spine42_v3_runtime_job_store_v2 import (
    P10Spine42V3RuntimeJobConflictV2,
    P10Spine42V3RuntimeJobStoreV2,
)
from .p10_spine42_v3_runtime_preflight_v2 import (
    P10Spine42V3RuntimePreflightV2,
    P10Spine42V3RuntimePreflightV2Error,
)
from .p10_spine42_v3_runtime_preflight_validation_v2 import (
    same_runtime_source_v2,
)
from .p10_spine42_v3_runtime_readback_v2 import (
    require_p10_spine42_v3_runtime_readback_v2,
)
from .spine42_v3_runtime_bundle_v2 import (
    Spine42V3RuntimeBundleV2,
    build_spine42_v3_runtime_bundle_v2,
)
from .spine42_v3_runtime_evidence_v2 import (
    build_spine42_v3_runtime_evidence_v2,
)
from .spine42_v3_runtime_reader_v2 import (
    Spine42V3RuntimeReaderV2Error,
    Spine42V3RuntimeV2NotFound,
    VerifiedSpine42V3RuntimeReaderV2,
)
from .spine42_v3_runtime_runner_v2 import (
    run_spine42_v3_runtime_capture_v2,
)
from .spine42_v3_runtime_store_v2 import Spine42V3RuntimeStoreV2

EXECUTION_FORMAT = "autospine-p10-spine42-v3-runtime-execution-v2"


class P10Spine42V3RuntimeExecutionV2Error(RuntimeError):
    """Path-free failure boundary for the one-shot execution driver."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3RuntimeExecutionResultV2:
    outcome: str
    runner_invoked: bool
    snapshot: object = field(repr=False)

    def public_document(self):
        return {
            "format": EXECUTION_FORMAT, "format_version": 2,
            "job_id": self.snapshot.job_id, "outcome": self.outcome,
            "status": self.snapshot.status,
            "stage": self.snapshot.head["stage"],
            "head_event_sha256": self.snapshot.head_event_sha256,
            "runner_invoked": self.runner_invoked,
            "runner_execution_authorized": False,
            "publication_authorized": False,
        }


def execute_p10_spine42_v3_runtime_job_v2(
    store, preflight, authority, permit, *,
    runner=run_spine42_v3_runtime_capture_v2,
    evidence_builder=build_spine42_v3_runtime_evidence_v2,
    bundle_builder=build_spine42_v3_runtime_bundle_v2,
    publisher_factory=Spine42V3RuntimeStoreV2,
    reader_factory=VerifiedSpine42V3RuntimeReaderV2,
    readback=require_p10_spine42_v3_runtime_readback_v2,
):
    """Consume one permit and either complete or terminally settle its job."""

    _require_dependencies(
        store, preflight, authority, runner, evidence_builder,
        bundle_builder, publisher_factory, reader_factory, readback,
    )
    try:
        context = authority.consume(permit)
    except P10Spine42V3RuntimeAuthorityV2Error as exc:
        raise P10Spine42V3RuntimeExecutionV2Error(
            "Runtime execution permit could not be consumed") from exc
    invoked = False
    try:
        try:
            fresh = preflight.refresh_for_execution(context.prepared)
            _require_fresh_context(fresh, context)
        except (P10Spine42V3RuntimePreflightV2Error, ValueError, TypeError):
            return _settle_from_claim(
                store, context, "failed_retryable",
                "execution_preflight_changed", "new_authorization", invoked,
            )
        snapshot = _append(
            store, context.job_id, context.head_event_sha256,
            "running", "runtime_reverified",
        )
        snapshot = _append(
            store, context.job_id, snapshot.head_event_sha256,
            "running", "capturing", current=0,
        )
        try:
            invoked = True
            run = runner(
                store.state_root, context.request.document["source"]["project_id"],
                skeleton_json_sha256=context.request.document["source"][
                    "skeleton_json_sha256"],
                spine42_v3_bundle_sha256=context.request.document["source"][
                    "spine42_v3_bundle_sha256"],
                expected_runtime=context.runtime,
                expected_browser=context.browser,
                license_acknowledged=True,
            )
        except Exception:
            return _settle(
                store, snapshot, "failed_retryable",
                "runtime_capture_failed", "new_authorization", invoked,
            )
        snapshot = _append(
            store, context.job_id, snapshot.head_event_sha256,
            "running", "capturing", current=1,
        )
        snapshot = _append(
            store, context.job_id, snapshot.head_event_sha256,
            "running", "evidence_compiling",
        )
        try:
            evidence = evidence_builder(run)
            bundle = bundle_builder(evidence)
            address = _address(bundle, context.request.document["source"])
        except Exception:
            return _settle(
                store, snapshot, "failed_terminal",
                "runtime_evidence_invalid", None, invoked,
            )
        snapshot = _append(
            store, context.job_id, snapshot.head_event_sha256,
            "running", "publishing", current=1, capture_address=address,
        )
        return _publish_and_readback(
            store, snapshot, evidence, address, publisher_factory,
            reader_factory, readback, invoked,
        )
    except P10Spine42V3RuntimeJobConflictV2:
        return _result("conflict_reloaded", store.load(context.job_id), invoked)
    except Exception as exc:
        raise P10Spine42V3RuntimeExecutionV2Error(
            "Runtime execution journal is unavailable") from exc


def _publish_and_readback(store, snapshot, evidence, address,
                          publisher_factory, reader_factory, readback, invoked):
    try:
        publisher_factory(store.state_root).publish(evidence)
    except Exception:
        pass
    try:
        exact = readback(
            reader_factory(store.state_root), snapshot, store.state_root,
        )
        if exact != address:
            raise Spine42V3RuntimeReaderV2Error(
                "Runtime exact readback address differs")
    except Spine42V3RuntimeV2NotFound:
        return _settle(
            store, snapshot, "failed_retryable",
            "capture_address_not_found", "new_authorization", invoked,
        )
    except Exception:
        return _settle(
            store, snapshot, "failed_terminal",
            "capture_readback_mismatch", None, invoked,
        )
    snapshot = _append(
        store, snapshot.job_id, snapshot.head_event_sha256,
        "running", "parent_exact_readback", capture_address=exact,
    )
    snapshot = _append(
        store, snapshot.job_id, snapshot.head_event_sha256,
        "completed", "completed", current=1, result=exact,
    )
    return _result("completed", snapshot, invoked)


def _settle_from_claim(store, context, status, code, resume, invoked):
    try:
        snapshot = store.append_event(
            context.job_id, status, "exact_source_readback",
            expected_previous_event_sha256=context.head_event_sha256,
            failure_code=code, resume_mode=resume,
        )
        return _result(status, snapshot, invoked)
    except P10Spine42V3RuntimeJobConflictV2:
        return _result(
            "conflict_reloaded", store.load(context.job_id), invoked)


def _settle(store, snapshot, status, code, resume, invoked):
    head = snapshot.head
    try:
        settled = store.append_event(
            snapshot.job_id, status, head["stage"],
            expected_previous_event_sha256=snapshot.head_event_sha256,
            current=head["progress"]["current"],
            total=head["progress"]["total"], failure_code=code,
            resume_mode=resume, capture_address=head["capture_address"],
        )
        return _result(status, settled, invoked)
    except P10Spine42V3RuntimeJobConflictV2:
        return _result(
            "conflict_reloaded", store.load(snapshot.job_id), invoked)


def _append(store, job_id, previous, status, stage, *, current=0,
            capture_address=None, result=None):
    return store.append_event(
        job_id, status, stage, expected_previous_event_sha256=previous,
        current=current, total=1, capture_address=capture_address,
        result=result,
    )


def _require_fresh_context(fresh, context):
    if fresh.request.canonical_bytes != context.request.canonical_bytes \
            or fresh.candidate.document != context.candidate.document \
            or not same_runtime_source_v2(fresh.source, context.source) \
            or fresh.environment.runtime != context.runtime \
            or fresh.environment.browser != context.browser:
        raise ValueError("Runtime execution inputs changed")


def _address(bundle, source):
    if type(bundle) is not Spine42V3RuntimeBundleV2:
        raise ValueError("Runtime evidence bundle type is invalid")
    address = {
        "project_id": bundle.project_id,
        "skeleton_json_sha256": bundle.skeleton_json_sha256,
        "spine42_v3_bundle_sha256": bundle.spine42_v3_bundle_sha256,
        "capture_bundle_sha256": bundle.bundle_sha256,
    }
    if bundle.clip_id != source["clip_id"] or any(
        address[name] != source[name] for name in (
            "project_id", "skeleton_json_sha256",
            "spine42_v3_bundle_sha256",
        )
    ):
        raise ValueError("Runtime evidence source differs")
    return address


def _require_dependencies(store, preflight, authority, *dependencies):
    if type(store) is not P10Spine42V3RuntimeJobStoreV2 \
            or type(preflight) is not P10Spine42V3RuntimePreflightV2 \
            or type(authority) is not P10Spine42V3RuntimeAuthorityV2 \
            or preflight.state_root != store.state_root \
            or any(not callable(value) for value in dependencies):
        raise P10Spine42V3RuntimeExecutionV2Error(
            "Runtime execution dependencies are invalid")


def _result(outcome, snapshot, invoked):
    return P10Spine42V3RuntimeExecutionResultV2(
        outcome, invoked, snapshot)


__all__ = [
    "EXECUTION_FORMAT", "P10Spine42V3RuntimeExecutionResultV2",
    "P10Spine42V3RuntimeExecutionV2Error",
    "execute_p10_spine42_v3_runtime_job_v2",
]
