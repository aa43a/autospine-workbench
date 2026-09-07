"""Pending annotation intake from a separately verified, accepted mapping."""

from ..resolved_project import canonical_sha256
from .validation import validate_benchmark_manifest


def build_annotation_template(manifest, decision):
    """Caller must exact-read decision; this template contains no ground truth."""
    validate_benchmark_manifest(manifest)
    if decision.get("schema") != "autospine.benchmark-mapping-decision/v1" \
            or decision.get("dataset_sha256") != canonical_sha256(manifest) \
            or decision.get("authority") != "none" \
            or decision.get("scope") != "benchmark_mapping_only" \
            or decision.get("decision_source") != "human_explicit" \
            or decision.get("action") != "accept" \
            or decision.get("mapping_status") != "reviewed_accepted":
        raise ValueError("benchmark_annotation_accepted_mapping_required")
    if not any(row["id"] == decision["character_id"] and row["dataset_split"] == "development"
               for row in manifest["characters"]):
        raise ValueError("benchmark_annotation_source_mismatch")
    return {"schema": "autospine.benchmark-annotation-template/v1", "authority": "none",
            "dataset_sha256": canonical_sha256(manifest), "character_id": decision["character_id"],
            "mapping_decision_sha256": canonical_sha256(decision),
            "source_candidate_sha256": decision["source_candidate_sha256"],
            "annotation_status": "pending", "coordinate_system": "pixel_top_left_y_down",
            "layer_semantics": [], "joint_observations": [], "rights": None}


def validate_annotation_template(manifest, decision, document):
    expected = build_annotation_template(manifest, decision)
    if canonical_sha256(expected) != canonical_sha256(document):
        raise ValueError("benchmark_annotation_template_mismatch")
    return expected
