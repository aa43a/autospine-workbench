"""Bounded, read-only inventory of historical P10.7a v2 completions."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat

from .p10_spine42_v3_completion_files_v2 import (
    require_p10_spine42_v3_completion_run_files_v2,
)
from .p10_spine42_v3_completion_provenance_v2 import (
    P10Spine42V3CompletionProvenanceV2Error,
    require_exact_p10_spine42_v3_success_v2,
    require_strict_p10_spine42_v3_row_v2,
)
from .p10_spine42_v3_job_v2 import (
    NAMESPACE, P10Spine42V3JobSnapshotV2, P10Spine42V3JobStoreV2,
)
from .resolved_project import canonical_sha256
from .spine42_bundle_files import (
    Spine42BundleFilesError, existing_exact_child, is_alias,
    require_real_directory,
)

MAX_RUNS = 10_000
_SHA = re.compile(r"^[0-9a-f]{64}$")
_UPSTREAM = ("job_id", "safety_run_id", "dynamic_run_id", "motion_run_id")
_SOURCE = (
    "project_id", "motion_instance_v3_sha256",
    "motion_instance_v3_bundle_sha256",
)
_FAMILY_ID_DOMAIN = "autospine-p10-spine42-v3-completion-family/v2"


class P10Spine42V3CompletionInventoryV2Error(RuntimeError):
    """Raised when the on-disk run namespace cannot be safely enumerated."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3CompletionSkipV2:
    spine_run_id: str
    code: str

    def public_document(self):
        return {"spine_run_id": self.spine_run_id, "code": self.code}


@dataclass(frozen=True, slots=True)
class P10Spine42V3CompletionFamilyV2:
    upstream: tuple[str, str, str, str]
    runs: tuple[P10Spine42V3JobSnapshotV2, ...]
    issue_code: str | None

    @property
    def family_id(self):
        return canonical_sha256({
            "domain": _FAMILY_ID_DOMAIN,
            "upstream": dict(zip(_UPSTREAM, self.upstream)),
        })

    @property
    def head(self):
        return None if self.issue_code is not None else self.runs[-1]

    def ambiguity_document(self):
        if self.issue_code is None:
            return None
        return {
            "family_id": self.family_id, "code": self.issue_code,
            "spine_run_ids": sorted(row.run_id for row in self.runs),
        }


@dataclass(frozen=True, slots=True)
class P10Spine42V3CompletionInventoryV2:
    families: tuple[P10Spine42V3CompletionFamilyV2, ...]
    skipped: tuple[P10Spine42V3CompletionSkipV2, ...]
    enumerated_run_ids: tuple[str, ...]

    @property
    def ambiguities(self):
        return tuple(
            row.ambiguity_document() for row in self.families
            if row.issue_code is not None
        )

    def family_containing(self, run_id):
        matches = [family for family in self.families
                   if any(row.run_id == run_id for row in family.runs)]
        return matches[0] if len(matches) == 1 else None


def read_p10_spine42_v3_completion_inventory_v2(state_root):
    """Load every exact run without consulting or repairing latest indexes."""

    entries = _read_run_entries(state_root)
    identifiers = tuple(run_id for run_id, _ in entries)
    try:
        store = P10Spine42V3JobStoreV2(state_root)
    except Exception as exc:
        raise P10Spine42V3CompletionInventoryV2Error(
            "P10.7a v2 completion store is unavailable") from exc
    loaded, skipped = [], []
    for run_id, directory in entries:
        try:
            require_p10_spine42_v3_completion_run_files_v2(directory)
            row = store.load(run_id)
            require_strict_p10_spine42_v3_row_v2(row)
        except Exception:
            skipped.append(P10Spine42V3CompletionSkipV2(
                run_id, "invalid_run"))
            continue
        if row.status == "completed":
            try:
                require_exact_p10_spine42_v3_success_v2(row)
            except P10Spine42V3CompletionProvenanceV2Error:
                skipped.append(P10Spine42V3CompletionSkipV2(
                    run_id, "invalid_provenance"))
                continue
        loaded.append(row)
    groups = {}
    for row in loaded:
        key = tuple(row.request[name] for name in _UPSTREAM)
        groups.setdefault(key, []).append(row)
    families = tuple(
        _validated_family(key, rows)
        for key, rows in sorted(groups.items())
    )
    return P10Spine42V3CompletionInventoryV2(
        families, tuple(skipped), identifiers)


def _read_run_entries(state_root):
    try:
        root = Path(os.path.abspath(os.fspath(Path(state_root))))
        root = require_real_directory(root, "P10.7a v2 inventory root")
        jobs = existing_exact_child(root, "jobs")
        if jobs is None:
            return ()
        jobs = require_real_directory(jobs, "P10.7a v2 jobs")
        family = existing_exact_child(jobs, NAMESPACE)
        if family is None:
            return ()
        family = require_real_directory(family, "P10.7a v2 runs")
        children = list(family.iterdir())
        if len(children) > MAX_RUNS:
            _fail("P10.7a v2 run inventory exceeds its bound")
        for child in children:
            if _SHA.fullmatch(child.name) is None or is_alias(child) \
                    or not stat.S_ISDIR(child.lstat().st_mode):
                _fail("P10.7a v2 run inventory is unsafe")
        # Sorting only stabilizes presentation; attempts determine every head.
        return tuple(sorted(
            ((child.name, child) for child in children),
            key=lambda item: item[0],
        ))
    except P10Spine42V3CompletionInventoryV2Error:
        raise
    except (OSError, TypeError, ValueError,
            Spine42BundleFilesError) as exc:
        raise P10Spine42V3CompletionInventoryV2Error(
            "P10.7a v2 run inventory cannot be read safely") from exc


def _validated_family(upstream, rows):
    ordered = sorted(rows, key=lambda row: row.request["attempt"])
    issue = _chain_issue(ordered)
    return P10Spine42V3CompletionFamilyV2(
        upstream, tuple(ordered), issue)


def _chain_issue(rows):
    attempts = [row.request["attempt"] for row in rows]
    if len(set(attempts)) != len(attempts):
        return "duplicate_attempt"
    if attempts != list(range(1, len(rows) + 1)):
        return "attempt_gap"
    baseline = tuple(rows[0].request[name] for name in _SOURCE)
    for index, row in enumerate(rows):
        expected = None if index == 0 else rows[index - 1].run_id
        if row.request["previous_run_id"] != expected:
            return "previous_run_mismatch"
        if not row.events:
            return "incomplete_attempt"
        if index and rows[index - 1].status != "failed_retryable":
            return "predecessor_not_retryable"
        if tuple(row.request[name] for name in _SOURCE) != baseline:
            return "source_drift"
    return None


def _fail(message):
    raise P10Spine42V3CompletionInventoryV2Error(message)


__all__ = [
    "MAX_RUNS", "P10Spine42V3CompletionFamilyV2",
    "P10Spine42V3CompletionInventoryV2",
    "P10Spine42V3CompletionInventoryV2Error",
    "P10Spine42V3CompletionSkipV2",
    "read_p10_spine42_v3_completion_inventory_v2",
]
