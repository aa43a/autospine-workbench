"""Issuer-private, one-shot, in-memory execution permits for P10.7b v2."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
import os
import threading
from weakref import WeakKeyDictionary

from .browser_executable_snapshot import BrowserExecutableSnapshot
from .p10_spine42_v3_runtime_job_snapshot_v2 import (
    P10Spine42V3RuntimeJobSnapshotV2,
)
from .p10_spine42_v3_runtime_job_store_v2 import (
    P10Spine42V3RuntimeJobStoreV2,
)
from .p10_spine42_v3_runtime_manager_owner_lease_v2 import (
    _require_acquired_p10_spine42_v3_runtime_manager_owner_lease_v2,
)
from .p10_spine42_v3_runtime_preflight_v2 import (
    _require_create_ready_p10_spine42_v3_runtime_preflight_v2,
)
from .spine42_runtime_inputs import Spine42RuntimePackage

_RECEIPT = object()
_GLOBAL_CLAIMS_LOCK = threading.Lock()
_GLOBAL_CLAIMS = set()


class P10Spine42V3RuntimeAuthorityV2Error(RuntimeError):
    """Path-free failure boundary for ephemeral execution authority."""


class _NotSerializable:
    def __copy__(self):
        raise TypeError("Runtime execution authority cannot be copied")

    def __deepcopy__(self, _memo):
        raise TypeError("Runtime execution authority cannot be copied")

    def __reduce_ex__(self, _protocol):
        raise TypeError("Runtime execution authority cannot be serialized")


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class P10Spine42V3RuntimeExecutionPermitV2(_NotSerializable):
    job_id: str
    head_event_sha256: str
    _receipt: InitVar[object] = None

    def __post_init__(self, _receipt):
        if _receipt is not _RECEIPT:
            raise P10Spine42V3RuntimeAuthorityV2Error(
                "Runtime execution permit is not issued")


@dataclass(frozen=True, slots=True)
class P10Spine42V3RuntimeExecutionInputsV2(_NotSerializable):
    job_id: str
    head_event_sha256: str
    prepared: object = field(repr=False)
    request: object = field(repr=False)
    candidate: object = field(repr=False)
    source: object = field(repr=False)
    runtime: Spine42RuntimePackage = field(repr=False)
    browser: BrowserExecutableSnapshot = field(repr=False)
    _receipt: InitVar[object] = None

    def __post_init__(self, _receipt):
        if _receipt is not _RECEIPT:
            raise P10Spine42V3RuntimeAuthorityV2Error(
                "Runtime execution inputs are not issued")


class P10Spine42V3RuntimeAuthorityV2:
    """Mint a permit only from a persisted exact-source-readback CAS head."""

    def __init__(self, job_store, owner_lease):
        try:
            if type(job_store) is not P10Spine42V3RuntimeJobStoreV2:
                raise ValueError
            owner_root, owner_epoch = (
                _require_acquired_p10_spine42_v3_runtime_manager_owner_lease_v2(
                    owner_lease
                )
            )
            if _root_scope(job_store.state_root) != owner_root:
                raise ValueError
        except Exception as exc:
            raise P10Spine42V3RuntimeAuthorityV2Error(
                "Runtime execution authority owner is invalid") from exc
        self._store, self._load = job_store, job_store.load
        self._owner = owner_lease
        self._owner_root, self._owner_epoch = owner_root, owner_epoch
        self._lock = threading.Lock()
        self._permits = WeakKeyDictionary()

    def issue(self, prepared, claimed_snapshot):
        try:
            owner_root = self._require_owner()
            details = _require_create_ready_p10_spine42_v3_runtime_preflight_v2(
                prepared
            )
            if _root_scope(details[0]) != owner_root:
                raise ValueError
            _require_claim(claimed_snapshot, details[-1])
            persisted = self._load(claimed_snapshot.job_id)
            if not _same_snapshot(persisted, claimed_snapshot):
                raise ValueError
            key = (
                owner_root, persisted.job_id, persisted.head_event_sha256,
            )
            with _GLOBAL_CLAIMS_LOCK:
                self._require_owner()
                if key in _GLOBAL_CLAIMS:
                    raise P10Spine42V3RuntimeAuthorityV2Error(
                        "Runtime execution claim was already used")
                permit = P10Spine42V3RuntimeExecutionPermitV2(
                    persisted.job_id, persisted.head_event_sha256, _RECEIPT,
                )
                with self._lock:
                    self._permits[permit] = (persisted, prepared, details)
                _GLOBAL_CLAIMS.add(key)
            return permit
        except P10Spine42V3RuntimeAuthorityV2Error:
            raise
        except Exception as exc:
            raise P10Spine42V3RuntimeAuthorityV2Error(
                "Runtime execution permit could not be issued") from exc

    def consume(self, permit):
        if type(permit) is not P10Spine42V3RuntimeExecutionPermitV2:
            raise P10Spine42V3RuntimeAuthorityV2Error(
                "Runtime execution permit is invalid")
        self._require_owner()
        with self._lock:
            issued = self._permits.pop(permit, None)
        if issued is None:
            raise P10Spine42V3RuntimeAuthorityV2Error(
                "Runtime execution permit is absent or consumed")
        claimed, prepared, details = issued
        try:
            persisted = self._load(claimed.job_id)
            if not _same_snapshot(persisted, claimed):
                raise ValueError
            _, _, candidate, source, environment, request = details
            if type(environment.runtime) is not Spine42RuntimePackage \
                    or type(environment.browser) is not BrowserExecutableSnapshot:
                raise ValueError
            self._require_owner()
            return P10Spine42V3RuntimeExecutionInputsV2(
                claimed.job_id, claimed.head_event_sha256,
                prepared, request, candidate, source,
                environment.runtime, environment.browser, _RECEIPT,
            )
        except P10Spine42V3RuntimeAuthorityV2Error:
            raise
        except Exception as exc:
            raise P10Spine42V3RuntimeAuthorityV2Error(
                "Runtime execution permit could not be consumed") from exc

    def revoke(self, permit):
        if type(permit) is not P10Spine42V3RuntimeExecutionPermitV2:
            raise P10Spine42V3RuntimeAuthorityV2Error(
                "Runtime execution permit is invalid")
        with self._lock:
            return self._permits.pop(permit, None) is not None

    def _require_owner(self):
        try:
            root, epoch = (
                _require_acquired_p10_spine42_v3_runtime_manager_owner_lease_v2(
                    self._owner
                )
            )
            if root != self._owner_root or epoch is not self._owner_epoch:
                raise ValueError
            return root
        except Exception as exc:
            raise P10Spine42V3RuntimeAuthorityV2Error(
                "Runtime execution authority owner is not active") from exc


def _require_claim(snapshot, request):
    if type(snapshot) is not P10Spine42V3RuntimeJobSnapshotV2 \
            or len(snapshot.events) != 2 \
            or snapshot.status != "running" \
            or snapshot.head["stage"] != "exact_source_readback" \
            or snapshot.head["progress"] != {"current": 0, "total": 1} \
            or snapshot.request.canonical_bytes != request.canonical_bytes \
            or snapshot.job_id != request.job_id:
        raise P10Spine42V3RuntimeAuthorityV2Error(
            "Runtime execution claim is invalid")


def _same_snapshot(left, right):
    return type(left) is P10Spine42V3RuntimeJobSnapshotV2 \
        and type(right) is P10Spine42V3RuntimeJobSnapshotV2 \
        and left.request.canonical_bytes == right.request.canonical_bytes \
        and tuple(event.canonical_bytes for event in left.events) == tuple(
            event.canonical_bytes for event in right.events
        )


def _root_scope(value):
    return os.path.normcase(os.path.abspath(os.fspath(value)))


__all__ = [
    "P10Spine42V3RuntimeAuthorityV2",
    "P10Spine42V3RuntimeAuthorityV2Error",
    "P10Spine42V3RuntimeExecutionInputsV2",
    "P10Spine42V3RuntimeExecutionPermitV2",
]
