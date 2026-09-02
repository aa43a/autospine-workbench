"""Canonical captured-unreviewed evidence for P10.7b v2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import threading
from typing import Any
from weakref import WeakKeyDictionary

from .spine42_v3_bundle_reader_v2 import VerifiedSpine42V3BundleV2
from .spine42_v3_runtime_evidence_contract_v2 import (
    ADMISSION_NAME, AUTHORITY, FIXED_NAMES, FORMAT, FORMAT_VERSION,
    MANIFEST_NAME, PLAN_NAME, RELEASE_GATE, REPORTS_NAME, SESSIONS_NAME,
    artifacts as _artifacts, captures as _captures, manifest as _manifest,
    manifest_from_stored as _manifest_from_stored, sha as _sha,
)
from .spine42_v3_runtime_capture_report import (
    require_capture_snapshot_consistency,
)
from .spine42_v3_runtime_plan_v2 import (
    canonical_spine42_v3_runtime_plan_bytes_v2,
    require_spine42_v3_runtime_plan_v2,
)
from .spine42_v3_runtime_profile_v2 import MAX_CAPTURE_ARTIFACTS
from .spine42_v3_runtime_runner_v2 import (
    Spine42V3RuntimeRunnerV2Error,
    _require_issued_spine42_v3_runtime_run_v2,
)
from .spine42_v3_runtime_session_core import canonical_json
from .spine42_v3_runtime_session_v2 import Spine42V3RuntimeSessionsV2
from .spine42_v3_runtime_source_admission_v2 import (
    canonical_spine42_v3_runtime_source_admission_bytes_v2,
    require_spine42_v3_runtime_source_admission_v2,
)


MAX_JSON_BYTES = 32 * 1024 * 1024
EVIDENCE_IDENTITY_DOMAIN = b"autospine.spine42-v3-runtime-evidence/v2\x00"


class Spine42V3RuntimeEvidenceV2Error(ValueError):
    """Raised unless captured v2 bytes replay exactly without review claims."""


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True)
class Spine42V3RuntimeEvidenceV2:
    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    spine42_v3_bundle_sha256: str
    evidence_sha256: str
    _file_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def file_items(self) -> tuple[tuple[str, bytes], ...]:
        return self._file_items

    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(dict(self._file_items)[MANIFEST_NAME])


_ISSUED_EVIDENCE = WeakKeyDictionary()
_ISSUED_EVIDENCE_LOCK = threading.Lock()


def build_spine42_v3_runtime_evidence_v2(run) -> Spine42V3RuntimeEvidenceV2:
    """Consume only one unchanged runner-issued transient capability."""

    try:
        bundle, source, runtime, browser, sessions, snapshot = (
            _require_issued_spine42_v3_runtime_run_v2(run)
        )
        plan_bytes = canonical_spine42_v3_runtime_plan_bytes_v2(sessions.plan)
        admission_bytes = canonical_spine42_v3_runtime_source_admission_bytes_v2(
            sessions.source_admission
        )
        report_bytes = _json_bytes(list(snapshot.reports), "reports")
        captures = snapshot.capture_bytes
        fixed = {
            PLAN_NAME: plan_bytes, ADMISSION_NAME: admission_bytes,
            SESSIONS_NAME: sessions.canonical_bytes, REPORTS_NAME: report_bytes,
        }
        artifacts = _artifacts(
            sessions.plan, captures, Spine42V3RuntimeEvidenceV2Error,
        )
        manifest = _manifest(
            bundle, source, runtime, browser, sessions, fixed, artifacts,
        )
        items = ((MANIFEST_NAME, _json_bytes(manifest, "manifest")),) + tuple(
            (name, fixed[name]) for name in FIXED_NAMES[1:]
        ) + tuple(
            (row["stored_path"], captures[row["artifact_id"]])
            for row in artifacts
        )
        evidence = replay_spine42_v3_runtime_evidence_v2(bundle, items)
        with _ISSUED_EVIDENCE_LOCK:
            _ISSUED_EVIDENCE[evidence] = bundle
        return evidence
    except Spine42V3RuntimeEvidenceV2Error:
        raise
    except (Spine42V3RuntimeRunnerV2Error, KeyError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeEvidenceV2Error(
            "Runtime evidence v2 requires an exact runner-issued capture"
        ) from exc


def replay_spine42_v3_runtime_evidence_v2(
    bundle: VerifiedSpine42V3BundleV2,
    file_items: tuple[tuple[str, bytes], ...],
) -> Spine42V3RuntimeEvidenceV2:
    """Detached semantic replay for storage and historical readers."""

    try:
        if type(bundle) is not VerifiedSpine42V3BundleV2:
            raise Spine42V3RuntimeEvidenceV2Error(
                "Runtime evidence v2 requires an exact P10.7a v2 bundle"
            )
        files = _files(file_items)
        manifest = _document(files[MANIFEST_NAME], "manifest")
        plan = require_spine42_v3_runtime_plan_v2(
            _document(files[PLAN_NAME], "plan"), bundle=bundle,
        )
        admission = require_spine42_v3_runtime_source_admission_v2(
            _document(files[ADMISSION_NAME], "admission"),
            bundle=bundle, plan=plan,
        )
        sessions = Spine42V3RuntimeSessionsV2(
            files[SESSIONS_NAME].decode("utf-8")
        )
        if sessions.plan != plan or sessions.source_admission != admission:
            raise Spine42V3RuntimeEvidenceV2Error(
                "Runtime session source differs from stored v2 contracts"
            )
        reports = _document_list(files[REPORTS_NAME], "reports")
        captures = _captures(
            manifest, files, plan, Spine42V3RuntimeEvidenceV2Error,
        )
        expected_order = FIXED_NAMES + tuple(
            row["stored_path"] for row in manifest["artifacts"]
        )
        if tuple(name for name, _raw in file_items) != expected_order:
            raise Spine42V3RuntimeEvidenceV2Error(
                "Runtime evidence v2 file order is invalid"
            )
        report_map = dict(zip(sessions.artifact_ids, reports, strict=True))
        require_capture_snapshot_consistency(
            sessions.artifact_ids, sessions.session_bytes, captures,
            report_map, error_type=Spine42V3RuntimeEvidenceV2Error,
        )
        fixed = {name: files[name] for name in FIXED_NAMES[1:]}
        expected = _manifest_from_stored(
            bundle, manifest, sessions, fixed,
            _artifacts(plan, captures, Spine42V3RuntimeEvidenceV2Error),
            Spine42V3RuntimeEvidenceV2Error,
        )
        if manifest != expected:
            raise Spine42V3RuntimeEvidenceV2Error(
                "Runtime capture manifest v2 differs from exact replay"
            )
        identity = _sha(EVIDENCE_IDENTITY_DOMAIN + b"".join(
            len(name.encode()).to_bytes(8, "big") + name.encode() +
            len(raw).to_bytes(8, "big") + raw for name, raw in file_items
        ))
        evidence = Spine42V3RuntimeEvidenceV2(
            bundle.project_id, bundle.clip_id, bundle.skeleton_json_sha256,
            bundle.bundle_sha256, identity, tuple(file_items),
        )
        return evidence
    except Spine42V3RuntimeEvidenceV2Error:
        raise
    except (KeyError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3RuntimeEvidenceV2Error(
            "Runtime evidence v2 replay failed"
        ) from exc


def _files(items):
    if type(items) is not tuple \
            or not len(FIXED_NAMES) + 4 <= len(items) <= \
            len(FIXED_NAMES) + MAX_CAPTURE_ARTIFACTS or any(
        type(row) is not tuple or len(row) != 2 or type(row[0]) is not str
        or type(row[1]) is not bytes for row in items
    ):
        raise Spine42V3RuntimeEvidenceV2Error("Evidence files are invalid")
    files = dict(items)
    if len(files) != len(items) or tuple(files)[:5] != FIXED_NAMES \
            or len({name.casefold() for name in files}) != len(files) \
            or any(not 0 < len(files[name]) <= MAX_JSON_BYTES
                   for name in FIXED_NAMES):
        raise Spine42V3RuntimeEvidenceV2Error("Evidence inventory is invalid")
    return files


def _require_issued_spine42_v3_runtime_evidence_v2(value):
    if type(value) is not Spine42V3RuntimeEvidenceV2:
        raise Spine42V3RuntimeEvidenceV2Error("Evidence v2 is not issued")
    with _ISSUED_EVIDENCE_LOCK:
        bundle = _ISSUED_EVIDENCE.get(value)
    if bundle is None:
        raise Spine42V3RuntimeEvidenceV2Error("Evidence v2 is not issued")
    replayed = replay_spine42_v3_runtime_evidence_v2(
        bundle, value.file_items,
    )
    names = tuple(value.__dataclass_fields__)
    actual = tuple(getattr(value, name) for name in names)
    expected = tuple(getattr(replayed, name) for name in names)
    if any(type(item) is not type(reference) or item != reference
           for item, reference in zip(actual, expected, strict=True)):
        raise Spine42V3RuntimeEvidenceV2Error("Issued evidence v2 changed")
    return bundle, value.file_items


def _document(raw, label):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_JSON_BYTES:
        raise Spine42V3RuntimeEvidenceV2Error(f"{label} is unbounded")
    value = json.loads(raw)
    if type(value) is not dict or _json_bytes(value, label) != raw:
        raise Spine42V3RuntimeEvidenceV2Error(f"{label} is not canonical")
    return value


def _document_list(raw, label):
    value = json.loads(raw)
    if type(value) is not list or _json_bytes(value, label) != raw:
        raise Spine42V3RuntimeEvidenceV2Error(f"{label} is not canonical")
    return value


def _json_bytes(value, label):
    raw = canonical_json(value).encode("utf-8")
    if not 0 < len(raw) <= MAX_JSON_BYTES:
        raise Spine42V3RuntimeEvidenceV2Error(f"{label} is unbounded")
    return raw


__all__ = [
    "ADMISSION_NAME", "AUTHORITY", "FIXED_NAMES", "FORMAT",
    "FORMAT_VERSION", "MANIFEST_NAME", "PLAN_NAME", "RELEASE_GATE",
    "REPORTS_NAME", "SESSIONS_NAME", "Spine42V3RuntimeEvidenceV2",
    "Spine42V3RuntimeEvidenceV2Error", "build_spine42_v3_runtime_evidence_v2",
    "replay_spine42_v3_runtime_evidence_v2",
]
