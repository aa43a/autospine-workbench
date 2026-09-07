"""Exact benchmark mapping decision reader; no inferred latest approval."""

from .artifacts import read_report
from .mapping_decision import validate_mapping_decision
from .validation import validate_benchmark_manifest


def read_mapping_decision(state_root, manifest, digest):
    validate_benchmark_manifest(manifest)
    dataset = manifest["dataset_id"]
    decision = read_report(state_root, dataset, "mapping-decisions", digest)
    candidate = read_report(state_root, dataset, "mapping-candidates", decision["source_candidate_sha256"])
    request = read_report(state_root, dataset, "mapping-review-requests", decision["source_request_sha256"])
    return validate_mapping_decision(manifest, candidate, request, decision)
