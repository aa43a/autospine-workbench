"""Append-only attempt journal for automatic P10.7a v2 publication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import stat

from .p10_capture_job_store import (
    _event_inventory, _exact_directory, _publish_once, _read,
)
from .p10_spine42_v3_attempt_index_v2 import (
    read_spine42_v3_latest_v2, write_spine42_v3_latest_v2,
)
from .p10_spine42_v3_auto_inputs_v2 import P10Spine42V3AutoInputsV2
from .p10_spine42_v3_job_contract_v2 import (
    ACTIVE, EVENT_FORMAT, P10Spine42V3JobV2Error, TERMINAL,
    canonical_bytes as _bytes, request_document as _request,
    require_event as _require_event, require_request as _require_request,
    require_sha as _require_sha, require_transition as _require_transition,
    run_id as _run_id,
)
from .resolved_project import canonical_sha256
from .safe_input_files import strict_json_object
from .spine42_bundle_files import require_real_directory

NAMESPACE = "body-sway-spine42-v3-jobs-v2"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_KEYS = ("job_id", "safety_run_id", "dynamic_run_id", "motion_run_id")


@dataclass(frozen=True, slots=True)
class P10Spine42V3JobSnapshotV2:
    request: dict
    events: tuple[dict, ...]

    @property
    def run_id(self):
        return _run_id(self.request)

    @property
    def status(self):
        return self.events[-1]["status"] if self.events else None

    @property
    def head_sha256(self):
        return self.events[-1]["event_sha256"] if self.events else None

    def public_document(self):
        head = self.events[-1] if self.events else {}
        return {
            "run_id": self.run_id, "status": self.status,
            "attempt": self.request["attempt"],
            "previous_run_id": self.request["previous_run_id"],
            "stage": head.get("stage"), "progress": head.get("progress"),
            "failure_code": head.get("failure_code"),
            "result": head.get("result"), "event_count": len(self.events),
            "head_event_sha256": self.head_sha256,
            "terminal": self.status in TERMINAL,
            "retryable": self.status == "failed_retryable",
        }


class P10Spine42V3JobStoreV2:
    def __init__(self, state_root):
        self.state_root = Path(state_root)
        require_real_directory(self.state_root, "P10.7a v2 state root")

    def create(self, inputs: P10Spine42V3AutoInputsV2, *, attempt,
               previous_run_id):
        request = _request(inputs, attempt, previous_run_id)
        existing = self.latest(*(getattr(inputs, key) for key in _KEYS))
        if existing is not None and existing.run_id == _run_id(request):
            return existing
        if existing is not None and (
            request["attempt"] != existing.request["attempt"] + 1
            or request["previous_run_id"] != existing.run_id
        ):
            raise P10Spine42V3JobV2Error(
                "P10.7a v2 attempt head is stale"
            )
        directory = self._run(_run_id(request), create=True)
        _publish_once(directory / "request.json", _bytes(request),
                      staging=directory, maximum=64 * 1024)
        _exact_directory(directory, "events", create=True)
        snapshot = self.load(_run_id(request))
        if snapshot.request != request:
            raise P10Spine42V3JobV2Error(
                "P10.7a v2 run address is occupied"
            )
        if not snapshot.events:
            snapshot = self.append(
                snapshot.run_id, "queued", "queued", expected_previous=None,
            )
        write_spine42_v3_latest_v2(
            self.state_root, snapshot.request, snapshot.run_id,
        )
        return snapshot

    def load(self, run_id):
        _require_sha(run_id)
        directory = self._run(run_id, create=False)
        request = strict_json_object(
            _read(directory / "request.json", 64 * 1024),
            "P10.7a v2 request",
        )
        _require_request(request)
        if _run_id(request) != run_id:
            raise P10Spine42V3JobV2Error(
                "P10.7a v2 request address differs"
            )
        events = []
        for sequence, path in _event_inventory(
            _exact_directory(directory, "events", create=False)
        ):
            event = strict_json_object(
                _read(path, 128 * 1024), "P10.7a v2 event",
            )
            _require_event(event, run_id, sequence)
            _require_transition(events[-1] if events else None, event)
            events.append(event)
        return P10Spine42V3JobSnapshotV2(request, tuple(events))

    def append(self, run_id, status, stage, *, expected_previous,
               current=0, total=1, failure_code=None, result=None):
        snapshot = self.load(run_id)
        if snapshot.head_sha256 != expected_previous:
            raise P10Spine42V3JobV2Error(
                "P10.7a v2 event head is stale"
            )
        payload = {
            "format": EVENT_FORMAT, "format_version": 2,
            "run_id": run_id, "sequence": len(snapshot.events) + 1,
            "previous_event_sha256": expected_previous,
            "status": status, "stage": stage,
            "progress": {"current": current, "total": total},
            "failure_code": failure_code, "result": result,
        }
        event = dict(payload)
        event["event_sha256"] = canonical_sha256({
            "domain": "autospine-p10-spine42-v3-job-event/v2",
            "event": payload,
        })
        _require_event(event, run_id, len(snapshot.events) + 1)
        _require_transition(snapshot.events[-1] if snapshot.events else None,
                            event)
        directory = self._run(run_id, create=False)
        _publish_once(
            _exact_directory(directory, "events", create=False)
            / f"{len(snapshot.events) + 1:06d}.json", _bytes(event),
            staging=directory, maximum=128 * 1024,
        )
        return self.load(run_id)

    def latest(self, job_id, safety_run_id, dynamic_run_id, motion_run_id):
        ids = (job_id, safety_run_id, dynamic_run_id, motion_run_id)
        try:
            index = read_spine42_v3_latest_v2(self.state_root, *ids)
        except Exception:
            return self._rebuild_latest(*ids)
        if index is None:
            return self._rebuild_latest(*ids)
        row = self.load(index["run_id"])
        checks = (*_KEYS, "attempt", "previous_run_id")
        if any(row.request[key] != index[key] for key in checks):
            raise P10Spine42V3JobV2Error(
                "P10.7a v2 latest index is cross-wired"
            )
        return row

    def _rebuild_latest(self, *ids):
        rows = [self.load(run_id) for run_id in self._run_ids()]
        rows = [row for row in rows if all(
            row.request[key] == value for key, value in zip(_KEYS, ids)
        )]
        if not rows:
            return None
        rows.sort(key=lambda item: item.request["attempt"])
        _require_attempt_chain(rows)
        row = rows[-1]
        write_spine42_v3_latest_v2(self.state_root, row.request, row.run_id)
        return row

    def recover_interrupted(self):
        recovered, groups = [], {}
        for run_id in self._run_ids():
            row = self.load(run_id)
            groups.setdefault(tuple(row.request[key] for key in _KEYS), []).append(row)
        for rows in groups.values():
            rows.sort(key=lambda item: item.request["attempt"])
            _require_attempt_chain(rows)
            row = rows[-1]
            if row.status in ACTIVE:
                row = self.append(
                    row.run_id, "failed_retryable", "failed",
                    expected_previous=row.head_sha256,
                    failure_code="process_restart",
                )
                recovered.append(row.run_id)
            write_spine42_v3_latest_v2(
                self.state_root, row.request, row.run_id,
            )
        return tuple(recovered)

    def _run(self, run_id, *, create):
        root = require_real_directory(self.state_root, "P10.7a v2 state root")
        jobs = _exact_directory(root, "jobs", create=create)
        family = _exact_directory(jobs, NAMESPACE, create=create)
        return _exact_directory(family, run_id, create=create)

    def _run_ids(self):
        root = require_real_directory(self.state_root, "P10.7a v2 state root")
        jobs = _exact_directory(root, "jobs", create=True)
        family = _exact_directory(jobs, NAMESPACE, create=True)
        children = list(family.iterdir())
        if len(children) > 10_000 or any(
            _SHA.fullmatch(row.name) is None
            or not stat.S_ISDIR(row.lstat().st_mode) for row in children
        ):
            raise P10Spine42V3JobV2Error(
                "P10.7a v2 run inventory is unsafe"
            )
        return tuple(sorted(row.name for row in children))


def _require_attempt_chain(rows):
    for position, row in enumerate(rows):
        previous = None if position == 0 else rows[position - 1].run_id
        if row.request["attempt"] != position + 1 \
                or row.request["previous_run_id"] != previous:
            raise P10Spine42V3JobV2Error(
                "P10.7a v2 attempt chain is ambiguous"
            )


__all__ = [
    "ACTIVE", "P10Spine42V3JobSnapshotV2", "P10Spine42V3JobStoreV2",
    "P10Spine42V3JobV2Error",
]
