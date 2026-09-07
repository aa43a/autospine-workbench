"""Pure benchmark aggregates: absent observations never count as successes."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
import re

from ..resolved_project import canonical_sha256
from ..automation.pipeline_profile import build_pipeline_profile
from ..automation.target_version import require_target_version
from .validation import validate_benchmark_manifest


OBSERVATIONS_SCHEMA = "autospine.benchmark-observations/v1"
METRICS_SCHEMA = "autospine.benchmark-metrics/v1"
SPLITS = ("development", "visible", "holdout", "reserve", "unassigned")
STATUSES = ("succeeded", "blocked", "failed", "not_run")
_OBSERVATION_KEYS = {"schema", "dataset_sha256", "code_commit", "profile", "target_version", "authority", "records"}
_RECORD_KEYS = {"character_id", "source_sha256", "status", "reason_code", "review_seconds", "auto_adoption_audit"}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_REASON = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")


class BenchmarkMetricsError(ValueError):
    """Stable reason for a rejected observation or dataset binding."""

    def __init__(self, reason_code="benchmark_observations_invalid"):
        self.reason_code = reason_code
        super().__init__(reason_code)


def validate_observations(manifest, observations):
    """Validate without inferring outcomes or auditing decisions automatically."""
    try:
        manifest = validate_benchmark_manifest(manifest)
        _object(observations, _OBSERVATION_KEYS)
        if observations["schema"] != OBSERVATIONS_SCHEMA or observations["authority"] != "none":
            raise BenchmarkMetricsError()
        if not _matches(_SHA, observations["dataset_sha256"]) or observations["dataset_sha256"] != canonical_sha256(manifest):
            raise BenchmarkMetricsError("benchmark_dataset_mismatch")
        if not _matches(_COMMIT, observations["code_commit"]):
            raise BenchmarkMetricsError()
        build_pipeline_profile(observations["profile"])
        require_target_version(observations["target_version"])
        characters = {row["id"]: row for row in manifest["characters"]}
        records = observations["records"]
        if type(records) is not list or len(records) > len(characters):
            raise BenchmarkMetricsError()
        seen = set()
        for row in records:
            _object(row, _RECORD_KEYS)
            identifier = row["character_id"]
            if type(identifier) is not str or identifier not in characters or identifier in seen:
                raise BenchmarkMetricsError("benchmark_character_invalid")
            seen.add(identifier)
            if row["source_sha256"] != characters[identifier]["source"]["sha256"]:
                raise BenchmarkMetricsError("benchmark_source_mismatch")
            _record(row)
        canonical_sha256(observations)
        return deepcopy(observations)
    except BenchmarkMetricsError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, OverflowError) as exc:
        raise BenchmarkMetricsError() from exc


def _record(row):
    status, reason = row["status"], row["reason_code"]
    if type(status) is not str or status not in STATUSES:
        raise BenchmarkMetricsError()
    if status in {"blocked", "failed"}:
        if not _matches(_REASON, reason):
            raise BenchmarkMetricsError()
    elif reason is not None:
        raise BenchmarkMetricsError()
    seconds = row["review_seconds"]
    if seconds is not None and (type(seconds) not in (int, float) or seconds < 0 or not math.isfinite(seconds)):
        raise BenchmarkMetricsError()
    audit = row["auto_adoption_audit"]
    if audit is not None:
        _object(audit, {"adopted", "checked", "correct"})
        if any(type(value) is not int or value < 0 for value in audit.values()) \
                or not audit["correct"] <= audit["checked"] <= audit["adopted"]:
            raise BenchmarkMetricsError()
    if status == "not_run" and (seconds is not None or audit is not None):
        raise BenchmarkMetricsError("benchmark_not_run_has_outcome")


def build_metrics(manifest, observations):
    """Use every assigned character as denominator; reserve is never primary."""
    observations = validate_observations(manifest, observations)
    manifest = validate_benchmark_manifest(manifest)
    records = {row["character_id"]: row for row in observations["records"]}
    ready = manifest["split_status"] == "frozen"
    groups = {split: [row for row in manifest["characters"] if row["dataset_split"] == split] for split in SPLITS}
    by_split = {split: _aggregate(rows, records, ready) for split, rows in groups.items()}
    primary = [row for split in SPLITS[:3] for row in groups[split]]
    return {
        "schema": METRICS_SCHEMA, "authority": "none", "dataset_id": manifest["dataset_id"],
        "dataset_sha256": canonical_sha256(manifest),
        "observations_sha256": canonical_sha256(observations),
        "code_commit": observations["code_commit"], "profile": observations["profile"],
        "target_version": observations["target_version"], "readiness": "ready" if ready else "not_ready",
        "overall": _aggregate(manifest["characters"], records, ready),
        "primary": _aggregate(primary, records, True) if ready else None,
        "reserve": by_split["reserve"] if ready else None,
        "by_split": by_split,
    }


def validate_metrics(manifest, observations, report):
    """Rebuild the report, including denominators, before trusting its numbers."""
    expected = build_metrics(manifest, observations)
    try:
        if type(report) is not dict or canonical_sha256(report) != canonical_sha256(expected):
            raise BenchmarkMetricsError("benchmark_metrics_mismatch")
    except (TypeError, ValueError, OverflowError) as exc:
        raise BenchmarkMetricsError("benchmark_metrics_mismatch") from exc
    return deepcopy(expected)


def _aggregate(characters, records, ready):
    present = [records[row["id"]] for row in characters if row["id"] in records]
    missing = len(characters) - len(present)
    statuses = Counter(row["status"] for row in present)
    statuses["not_run"] += missing
    reasons = Counter(row["reason_code"] for row in present if row["status"] in {"blocked", "failed"})
    seconds = sorted(float(row["review_seconds"]) for row in present if row["review_seconds"] is not None)
    audits = [row["auto_adoption_audit"] for row in present if row["auto_adoption_audit"] is not None]
    totals = {key: sum(row[key] for row in audits) if audits else None for key in ("adopted", "checked", "correct")}
    return {
        "total_characters": len(characters), "recorded_characters": len(present),
        "missing_observations": missing,
        "status_counts": {status: statuses[status] for status in STATUSES},
        "failure_reasons": dict(sorted(reasons.items())),
        "completion_rate": statuses["succeeded"] / len(characters) if ready and characters else None,
        "review_seconds": {"count": len(seconds), "p50": _percentile(seconds, .5), "p90": _percentile(seconds, .9)},
        "auto_adoption": {
            **totals, "accuracy": totals["correct"] / totals["checked"] if totals["checked"] else None,
            "coverage": None,
        },
    }


def _percentile(values, quantile):
    if not values:
        return None
    position = (len(values) - 1) * quantile
    lower = int(position)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (position - lower)


def _object(value, keys):
    if type(value) is not dict or set(value) != keys:
        raise BenchmarkMetricsError()


def _matches(pattern, value):
    return type(value) is str and pattern.fullmatch(value) is not None
