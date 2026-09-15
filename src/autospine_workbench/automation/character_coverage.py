"""Source-layer accounting for a verified preview; no animation or adoption claims."""

from collections import Counter
from copy import deepcopy

from ..resolved_project import canonical_sha256
from ..manifest_artifacts import require_sha256

SCHEMA = "autospine.character-coverage/v1"
STATES = {"weighted_candidate", "rigid_reviewed", "static_reference",
          "missing", "excluded", "not_visible", "partial"}


def _index(rows, key):
    result = {}
    for row in rows:
        name = row[key]
        if not isinstance(name, str) or not name or name in result:
            raise ValueError("character_coverage_duplicate_identity")
        result[name] = row
    return result


def build_coverage(candidate, draft, bindings, expanded_layers, scope, bundle_sha256):
    """Account for all sources using explicit expansion provenance, never name suffixes."""
    from ..targets.spine43.source_visibility import normalize
    profile = scope.get('visibility_profile')
    sources = _index([normalize(r, profile) for r in candidate["layers"]], "layer_id")
    decisions = _index(draft["records"], "layer_id")
    options = _index(bindings["bindings"], "layer_id")
    expanded = _index([normalize(r, profile) for r in expanded_layers], "layer_id")
    regions = _index(scope["regions"], "id")
    if set(sources) != set(decisions) or set(sources) != set(options):
        raise ValueError("character_coverage_source_mismatch")
    if not set(regions) <= set(expanded):
        raise ValueError("character_coverage_unknown_region")
    grouped = {name: [] for name in sources}
    for name, layer in expanded.items():
        parent = layer.get("source_layer_id", name)
        if parent not in sources:
            raise ValueError("character_coverage_unknown_source")
        grouped[parent].append(name)
    rows = []
    for name, source in sources.items():
        decision = decisions[name]
        chosen = next((o for o in options[name]["options"]
                       if o["id"] == decision.get("option_id")), None)
        rigid = decision["action"] == "bind" and chosen and chosen["mode"] == "rigid"
        outputs = []
        for child in grouped[name]:
            if child not in regions:
                continue
            kind = regions[child]["source_mesh_status"]
            if kind not in {"candidate", "rigid_context"}:
                raise ValueError("character_coverage_region_status_invalid")
            state = "weighted_candidate" if kind == "candidate" else (
                "rigid_reviewed" if rigid and child == name else "static_reference")
            outputs.append({"region_id": child, "state": state})
        absent = [child for child in grouped[name] if child not in regions
                  and not expanded[child].get("empty") and expanded[child].get("visible", True)]
        reasons = sorted({r["reason_code"] for r in scope["review_items"]
                          if r.get("layer_id") in {name, *grouped[name]}})
        if decision["action"] == "exclude":
            if outputs:
                raise ValueError("character_coverage_excluded_rendered")
            state = "excluded"
        elif source.get("empty") or not source.get("visible", True):
            if outputs:
                raise ValueError("character_coverage_hidden_rendered")
            state = "not_visible"
        elif not outputs:
            state = "missing"
            reasons.append("source_layer_not_rendered")
        else:
            states = {o["state"] for o in outputs}
            state = next(iter(states)) if len(states) == 1 and not absent else "partial"
            if absent:
                reasons.append("source_region_not_rendered")
            if "static_reference" in states:
                reasons.append("static_reference_not_bound")
        rows.append({"layer_id": name, "name": source.get("name", name), "state": state,
                     "regions": outputs, "missing_region_ids": absent if state not in {"excluded", "not_visible"} else [],
                     "reason_codes": sorted(set(reasons))})
    counts = Counter(row["state"] for row in rows)
    result = {"schema": SCHEMA, "authority": "none", "production_authorized": False,
              "full_character_animation": False, "preview_bundle_sha256": bundle_sha256,
              "source_addresses": deepcopy(scope["source_addresses"]),
              "layers": rows, "summary": {"source_layers": len(rows), "output_regions": len(regions),
                  "states": {state: counts[state] for state in sorted(STATES)}},
              "project_reason_codes": sorted({r["reason_code"] for r in scope["review_items"]
                                                if not r.get("layer_id")})}
    return result


def validate_coverage(document):
    """Validate public accounting invariants and reject inflated completion claims."""
    if document.get("schema") != SCHEMA or document.get("authority") != "none" \
            or document.get("production_authorized") is not False \
            or document.get("full_character_animation") is not False:
        raise ValueError("character_coverage_invalid")
    _index(document["layers"], "layer_id")
    require_sha256(document["preview_bundle_sha256"], "Preview bundle")
    for row in document["layers"]:
        if row["state"] not in STATES or row["reason_codes"] != sorted(set(row["reason_codes"])):
            raise ValueError("character_coverage_invalid")
        states = {r["state"] for r in row["regions"]}
        if not states <= {"weighted_candidate", "rigid_reviewed", "static_reference"}:
            raise ValueError("character_coverage_invalid")
        if row["state"] in {"excluded", "not_visible", "missing"} and row["regions"]:
            raise ValueError("character_coverage_invalid")
        if row["state"] in {"weighted_candidate", "rigid_reviewed", "static_reference"} \
                and (states != {row["state"]} or row["missing_region_ids"]):
            raise ValueError("character_coverage_invalid")
    outputs = [r for layer in document["layers"] for r in layer["regions"]]
    _index(outputs, "region_id")
    counts = Counter(row["state"] for row in document["layers"])
    if not set(counts) <= STATES or document["summary"] != {
        "source_layers": len(document["layers"]), "output_regions": len(outputs),
        "states": {state: counts[state] for state in sorted(STATES)}
    }:
        raise ValueError("character_coverage_invalid")
    return canonical_sha256(document)
