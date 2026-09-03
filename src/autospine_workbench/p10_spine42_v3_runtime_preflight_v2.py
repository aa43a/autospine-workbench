"""Read-only exact request preparation for automatic P10.7b v2 jobs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
import threading
from weakref import WeakKeyDictionary

from .p10_runtime_environment import (
    P10RuntimeEnvironment, discover_p10_runtime_environment,
)
from .p10_spine42_v3_runtime_job_contract_v2 import (
    P10Spine42V3RuntimeJobRequestV2,
)
from .p10_spine42_v3_runtime_job_files_v2 import normalized_state_root
from .p10_spine42_v3_runtime_preflight_validation_v2 import (
    SOURCE_FIELDS, require_automatic_selection_v2,
    require_preflight_payload_v2, same_runtime_source_v2,
    source_matches_candidate_output_v2,
)
from .spine42_v3_runtime_candidate_catalog_v2 import (
    read_spine42_v3_runtime_candidate_catalog_v2,
    revalidate_spine42_v3_runtime_candidate_entry_v2,
)
from .spine42_v3_runtime_candidate_contract_v2 import (
    Spine42V3RuntimeCandidateV2,
)
from .spine42_v3_runtime_source_bridge_v2 import (
    VerifiedSpine42V3RuntimeSourceBridgeV2,
    VerifiedSpine42V3RuntimeSourceV2,
)

FORMAT = "autospine-p10-spine42-v3-runtime-preflight-v2"
SELECTION_SOURCES = frozenset({"automatic", "explicit"})


class P10Spine42V3RuntimePreflightV2Error(RuntimeError):
    """Path-free failure boundary for request preparation."""


def _issued_preflight_types():
    receipt = object()
    issued = WeakKeyDictionary()
    issued_lock = threading.Lock()

    @dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
    class P10Spine42V3RuntimePreparedRequestV2:
        selection_source: str
        candidate: Spine42V3RuntimeCandidateV2 = field(repr=False)
        source: VerifiedSpine42V3RuntimeSourceV2 = field(repr=False)
        environment: P10RuntimeEnvironment = field(repr=False)
        request: P10Spine42V3RuntimeJobRequestV2 = field(repr=False)
        _receipt: InitVar[object] = None

        def __post_init__(self, _receipt):
            if _receipt is not receipt:
                raise P10Spine42V3RuntimePreflightV2Error(
                    "Runtime preflight value is not issued")

        def public_document(self):
            source = self.source
            return {
                "format": FORMAT, "format_version": 2,
                "selection_source": self.selection_source,
                "candidate": {
                    "candidate_id": self.candidate.candidate_id,
                    "entry_sha256": self.candidate.entry_sha256,
                    "spine_run_id": self.candidate.spine_run_id,
                },
                "source": {
                    name: getattr(source, name) for name in SOURCE_FIELDS
                },
                "environment": self.environment.public_document(),
                "request": {
                    "job_id": self.request.job_id,
                    "document": self.request.document,
                },
                "runner_execution_authorized": False,
                "publication_authorized": False,
            }

    def issue(root, phase, selection, candidate, source, environment, request):
        value = P10Spine42V3RuntimePreparedRequestV2(
            selection, candidate, source, environment, request, receipt,
        )
        with issued_lock:
            issued[value] = (
                root, phase, selection, candidate, source,
                environment, request,
            )
        return value

    def require(value, *, phase=None):
        if type(value) is not P10Spine42V3RuntimePreparedRequestV2:
            raise P10Spine42V3RuntimePreflightV2Error(
                "Runtime preflight value is invalid")
        with issued_lock:
            recorded = issued.get(value)
        actual = (
            value.selection_source, value.candidate, value.source,
            value.environment, value.request,
        )
        if recorded is None or (phase is not None and recorded[1] != phase) \
                or actual[0] != recorded[2] or any(
            left is not right for left, right in zip(actual[1:], recorded[3:])
        ):
            raise P10Spine42V3RuntimePreflightV2Error(
                "Runtime preflight value changed")
        return recorded

    def require_create_ready(value):
        recorded = require(value, phase="create_ready")
        return (recorded[0], *recorded[2:])

    class P10Spine42V3RuntimePreflightV2:
        """Prepare once, then fresh-revalidate before store.create."""

        def __init__(
            self, state_root, *,
            candidate_revalidator=(
                revalidate_spine42_v3_runtime_candidate_entry_v2),
            catalog_reader=read_spine42_v3_runtime_candidate_catalog_v2,
            bridge_factory=VerifiedSpine42V3RuntimeSourceBridgeV2,
            environment_discovery=discover_p10_runtime_environment,
        ):
            try:
                self.state_root = normalized_state_root(state_root)
                dependencies = (
                    candidate_revalidator, catalog_reader, bridge_factory,
                    environment_discovery,
                )
                if any(not callable(value) for value in dependencies):
                    raise TypeError
                (self._revalidate, self._catalog, self._bridge,
                 self._environment) = dependencies
            except Exception as exc:
                raise P10Spine42V3RuntimePreflightV2Error(
                    "Runtime preflight is unavailable") from exc

        def prepare(self, payload: Mapping, *, selection_source: str):
            """Use only fresh catalog/source/environment observations."""
            try:
                if type(selection_source) is not str \
                        or selection_source not in SELECTION_SOURCES \
                        or not isinstance(payload, Mapping):
                    raise P10Spine42V3RuntimePreflightV2Error(
                        "Runtime preflight request is invalid")
                require_preflight_payload_v2(payload)
                candidate_id, entry_sha256 = (
                    payload["candidate_id"], payload["entry_sha256"]
                )
                candidate = self._revalidate(
                    self.state_root, candidate_id, entry_sha256)
                source = self._build_source(candidate)
                environment = self._fresh_environment()
                request = self._request(payload, candidate, environment)
                self._require_selection(
                    selection_source, candidate_id, entry_sha256)
                return issue(
                    self.state_root, "prepared", selection_source,
                    candidate, source, environment, request,
                )
            except P10Spine42V3RuntimePreflightV2Error:
                raise
            except Exception as exc:
                raise P10Spine42V3RuntimePreflightV2Error(
                    "Runtime preflight request could not be prepared") from exc

        def refresh_for_create(self, expected):
            """Re-observe every mutable boundary immediately before create."""
            return self._refresh(
                expected, required_phase="prepared", next_phase="create_ready",
            )

        def refresh_for_execution(self, expected):
            """Re-observe a create-ready value immediately before execution."""
            return self._refresh(
                expected, required_phase="create_ready",
                next_phase="execution_ready",
            )

        def _refresh(self, expected, *, required_phase, next_phase):
            try:
                (root, _phase, selection, old_candidate, old_source,
                 old_environment, old_request) = require(
                    expected, phase=required_phase,
                )
                if root != self.state_root:
                    raise ValueError
                row = old_request.document
                candidate = self._revalidate(
                    self.state_root, row["candidate_id"], row["entry_sha256"])
                if type(candidate) is not Spine42V3RuntimeCandidateV2 \
                        or candidate.document != old_candidate.document:
                    raise ValueError
                source = self._bridge(self.state_root).rebuild_and_verify(
                    old_source)
                if type(source) is not VerifiedSpine42V3RuntimeSourceV2 \
                        or not same_runtime_source_v2(source, old_source):
                    raise ValueError
                environment = self._fresh_environment()
                if environment != old_environment:
                    raise ValueError
                payload = {name: row[name] for name in _PAYLOAD_FIELDS}
                request = self._request(payload, candidate, environment)
                if request.canonical_bytes != old_request.canonical_bytes:
                    raise ValueError
                self._require_selection(
                    selection, row["candidate_id"], row["entry_sha256"])
                return issue(
                    self.state_root, next_phase, selection, candidate,
                    source, environment, request,
                )
            except P10Spine42V3RuntimePreflightV2Error:
                raise
            except Exception as exc:
                raise P10Spine42V3RuntimePreflightV2Error(
                    "Runtime preflight changed before job creation") from exc

        def _require_selection(self, selection, candidate_id, entry_sha256):
            if selection != "automatic":
                return
            require_automatic_selection_v2(
                self._catalog(self.state_root), candidate_id, entry_sha256,
            )

        def _build_source(self, candidate):
            if type(candidate) is not Spine42V3RuntimeCandidateV2:
                raise ValueError
            output = candidate.document["completion"]["output"]
            source = self._bridge(self.state_root).build(
                output["project_id"], output["skeleton_json_sha256"],
                output["bundle_sha256"],
            )
            if type(source) is not VerifiedSpine42V3RuntimeSourceV2 \
                    or not source_matches_candidate_output_v2(source, output):
                raise ValueError
            return source

        def _fresh_environment(self):
            value = self._environment(self.state_root)
            if type(value) is not P10RuntimeEnvironment or not value.available:
                raise ValueError
            return value

        @staticmethod
        def _request(payload, candidate, environment):
            output = candidate.document["completion"]["output"]
            return P10Spine42V3RuntimeJobRequestV2.expand(
                payload, project_id=output["project_id"],
                clip_id=output["clip_id"],
                skeleton_json_sha256=output["skeleton_json_sha256"],
                spine42_v3_bundle_sha256=output["bundle_sha256"],
                runtime=environment.runtime, browser=environment.browser,
            )

    return (
        P10Spine42V3RuntimePreparedRequestV2,
        P10Spine42V3RuntimePreflightV2, require, require_create_ready,
    )


(
    P10Spine42V3RuntimePreparedRequestV2,
    P10Spine42V3RuntimePreflightV2,
    _require_issued_p10_spine42_v3_runtime_preflight_v2,
    _require_create_ready_p10_spine42_v3_runtime_preflight_v2,
) = _issued_preflight_types()
_PAYLOAD_FIELDS = (
    "candidate_id", "entry_sha256", "authorization_id", "retry_of_job_id",
    "explicit_runtime_license_confirmation", "explicit_run_confirmation",
)
__all__ = [
    "FORMAT", "P10Spine42V3RuntimePreflightV2",
    "P10Spine42V3RuntimePreflightV2Error",
    "P10Spine42V3RuntimePreparedRequestV2", "SELECTION_SOURCES",
]
