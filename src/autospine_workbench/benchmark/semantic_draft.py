"""Unapproved layer annotations, kept separate from algorithm suggestions."""

from copy import deepcopy
import unicodedata

from ..resolved_project import canonical_sha256
from .semantic_candidates import VOCABULARY

SCHEMA = "autospine.benchmark-semantic-draft/v1"
SIDES = ("unknown", "left", "right", "bilateral")
DISPOSITIONS = ("undecided", "include", "exclude")


def build_semantic_draft(candidate):
    return validate_semantic_draft(candidate, {
        "schema": SCHEMA, "candidate_sha256": canonical_sha256(candidate), "authority": "none",
        "records": [{"layer_id": row["layer_id"], "semantic": None, "side": "unknown",
                     "disposition": "undecided", "notes": ""} for row in candidate["layers"]],
    })


def validate_semantic_draft(candidate, draft):
    """Caller must validate candidate closure; drafts cannot claim acceptance."""
    if candidate.get("schema") != "autospine.benchmark-semantic-candidates/v1" or candidate.get("authority") != "none":
        raise ValueError("benchmark_semantic_candidate_invalid")
    if type(draft) is not dict or set(draft) != {"schema", "candidate_sha256", "authority", "records"} \
            or draft["schema"] != SCHEMA or draft["authority"] != "none" \
            or draft["candidate_sha256"] != canonical_sha256(candidate):
        raise ValueError("benchmark_semantic_draft_mismatch")
    records = draft["records"]
    if type(records) is not list or len(records) != len(candidate["layers"]):
        raise ValueError("benchmark_semantic_draft_layers_invalid")
    expected = {row["layer_id"] for row in candidate["layers"]}
    seen = set()
    for row in records:
        if type(row) is not dict or set(row) != {"layer_id", "semantic", "side", "disposition", "notes"}:
            raise ValueError("benchmark_semantic_draft_record_invalid")
        if type(row["layer_id"]) is not str or row["layer_id"] not in expected or row["layer_id"] in seen:
            raise ValueError("benchmark_semantic_draft_layers_invalid")
        seen.add(row["layer_id"])
        if row["semantic"] is not None and (type(row["semantic"]) is not str or row["semantic"] not in VOCABULARY):
            raise ValueError("benchmark_semantic_draft_role_invalid")
        if row["side"] not in SIDES or row["disposition"] not in DISPOSITIONS:
            raise ValueError("benchmark_semantic_draft_record_invalid")
        notes = row["notes"]
        if type(notes) is not str or len(notes) > 1000 or any(unicodedata.category(c).startswith("C") for c in notes):
            raise ValueError("benchmark_semantic_draft_notes_invalid")
    return deepcopy(draft)
