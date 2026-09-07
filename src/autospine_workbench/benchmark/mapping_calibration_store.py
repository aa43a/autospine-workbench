"""Read a calibration through its exact input closure and recompute it."""

from .artifacts import read_report
from .mapping import validate_mapping_candidate
from .mapping_anchors import validate_mapping_calibration
from .validation import validate_benchmark_manifest


def read_mapping_calibration(state_root, manifest, digest):
    validate_benchmark_manifest(manifest)
    dataset = manifest["dataset_id"]
    report = read_report(state_root, dataset, "mapping-calibrations", digest)
    candidate = read_report(state_root, dataset, "mapping-candidates", report["candidate_sha256"])
    anchors = read_report(state_root, dataset, "mapping-anchors", report["anchors_sha256"])
    validate_mapping_candidate(manifest, candidate)
    return validate_mapping_calibration(candidate, anchors, report)
