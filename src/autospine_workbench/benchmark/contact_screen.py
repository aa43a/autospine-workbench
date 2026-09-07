"""Non-authoritative clothing-contact screening without dropping evidence."""
from copy import deepcopy
import math

from ..resolved_project import canonical_sha256
from .contact_probe import RELATIONS, WARNINGS

SCHEMA = "autospine.benchmark-contact-screen/v1"
# Numeric snapshot of limb_geometry_matching v1; never reuse as anatomy proof.
THRESHOLDS = {"pelvis_leg": {"warn_overlap_ratio": 0.10, "warn_child_height_ratio": 0.20,
                            "reject_overlap_ratio": 0.25, "reject_child_height_ratio": 0.35}}
STATUSES = ("rejected_deep_overlap", "review_required", "local_contact_candidate")


def _require(condition):
    if not condition:
        raise ValueError("benchmark_contact_screen_input_invalid")


def _number(value, low, high):
    _require(type(value) in (int, float) and low <= value <= high and math.isfinite(value))


def _inputs(candidate, probe):
    _require(type(candidate) is dict and candidate.get("authority") == "none"
             and candidate.get("schema") == "autospine.benchmark-semantic-candidates/v1")
    canvas = candidate.get("canvas")
    _require(type(canvas) is list and len(canvas) == 2
             and all(type(v) is int and 0 < v <= 4096 for v in canvas))
    layers = candidate.get("layers")
    _require(type(layers) is list and 0 < len(layers) <= 256)
    by_id = {}
    for layer in layers:
        _require(type(layer) is dict and type(layer.get("layer_id")) is str)
        _require(layer["layer_id"] not in by_id)
        box = layer.get("bbox")
        _require(type(box) is list and len(box) == 4 and all(type(v) is int for v in box)
                 and box[0] <= box[2] and box[1] <= box[3])
        by_id[layer["layer_id"]] = layer
    _require(type(probe) is dict and probe.get("schema") == "autospine.benchmark-contact-probe/v1"
             and probe.get("authority") == "none" and probe.get("candidate_sha256") == canonical_sha256(candidate)
             and probe.get("algorithm_profile") == "raw-layer-contact-probe-v1"
             and probe.get("canvas") == canvas and probe.get("coordinate_system") == "psd_canvas"
             and type(probe.get("alpha_threshold_exclusive")) is int and probe["alpha_threshold_exclusive"] == 8
             and type(probe.get("max_gap_px")) is int and probe["max_gap_px"] == 8)
    relations = probe.get("relations")
    _require(type(relations) is list and len(relations) == 3)
    seen_contacts, pair_count = set(), 0
    for row, expected in zip(relations, RELATIONS):
        _require(type(row) is dict and row.get("relation") == expected[0])
        reasons = row.get("reason_codes")
        _require(type(reasons) is list and all(type(s) is str for s in reasons)
                 and all(s in reasons for s in WARNINGS))
        pairs = row.get("pairs")
        _require(type(pairs) is list)
        seen_pairs = set()
        for pair in pairs:
            _require(type(pair) is dict)
            ids = pair.get("layer_ids")
            _require(type(ids) is list and len(ids) == 2 and all(type(s) is str and s in by_id for s in ids)
                     and ids[0] != ids[1] and tuple(ids) not in seen_pairs)
            seen_pairs.add(tuple(ids))
            pair_count += 1
            _require(pair_count <= 64)
            child = by_id[ids[1]]["bbox"]
            _require(0 <= child[0] < child[2] <= canvas[0] and 0 <= child[1] < child[3] <= canvas[1])
            contacts = pair.get("contacts")
            _require(type(contacts) is list)
            for contact in contacts:
                _require(type(contact) is dict and type(contact.get("contact_id")) is str
                         and contact["contact_id"] not in seen_contacts and contact.get("joint_id") is None
                         and contact.get("relation") == row["relation"] and contact.get("layer_ids") == ids
                         and contact.get("mode") in ("overlap", "gap"))
                seen_contacts.add(contact["contact_id"])
                box, ratios = contact.get("bbox_xywh"), contact.get("overlap_ratios")
                _require(type(box) is list and len(box) == 4 and all(type(v) is int for v in box)
                         and 0 <= box[0] < canvas[0] and 0 <= box[1] < canvas[1]
                         and 0 < box[2] <= canvas[0]-box[0] and 0 < box[3] <= canvas[1]-box[1])
                _require(type(ratios) is list and len(ratios) == 2)
                for ratio in ratios:
                    _number(ratio, 0, 1)
                _number(contact.get("gap_distance_px"), 0, 8)
    return by_id


def _screen(contact, child_height, relation, multiple):
    ratio = contact["bbox_xywh"][3] / child_height
    reasons = list(multiple)
    if contact["mode"] == "gap":
        reasons.append("gap_contact_requires_review")
    if relation != "pelvis_leg":
        reasons.append("relation_thresholds_uncalibrated")
        status = "review_required"
    else:
        t = THRESHOLDS[relation]
        overlap = contact["mode"] == "overlap"
        if overlap and (contact["overlap_ratios"][1] >= t["reject_overlap_ratio"]
                        or ratio >= t["reject_child_height_ratio"]):
            reasons.append("clothing_overlap_too_deep")
            status = "rejected_deep_overlap"
        else:
            if overlap and (contact["overlap_ratios"][1] >= t["warn_overlap_ratio"]
                            or ratio >= t["warn_child_height_ratio"]):
                reasons.append("clothing_overlap_ambiguous")
            status = "review_required" if reasons else "local_contact_candidate"
            if not reasons:
                reasons.append("local_geometry_only")
    return {"contact_id": contact["contact_id"], "geometry_status": status,
            "reason_codes": reasons, "child_height_ratio": ratio, "joint_id": None}


def build_contact_screen(candidate, probe):
    """Caller must replay probe against pixels first; this adds diagnostics only."""
    try:
        layers = _inputs(candidate, probe)
        relations, summary = [], {"total": 0, **dict.fromkeys(STATUSES, 0)}
        for relation in probe["relations"]:
            multiple = ["multiple_layer_pairs"] if len(relation["pairs"]) > 1 else []
            pairs = []
            for pair in relation["pairs"]:
                reasons = multiple + (["multiple_contact_regions"] if len(pair["contacts"]) > 1 else [])
                box = layers[pair["layer_ids"][1]]["bbox"]
                contacts = [_screen(c, box[3]-box[1], relation["relation"], reasons) for c in pair["contacts"]]
                for contact in contacts:
                    summary["total"] += 1
                    summary[contact["geometry_status"]] += 1
                pairs.append({"layer_ids": deepcopy(pair["layer_ids"]), "reason_codes": reasons, "contacts": contacts})
            relations.append({"relation": relation["relation"], "role_status": "unreviewed_clothing_proxy",
                              "reason_codes": deepcopy(relation["reason_codes"]) + multiple, "pairs": pairs})
        return {"schema": SCHEMA, "authority": "none", "diagnostic_only": True,
                "candidate_sha256": canonical_sha256(candidate), "probe_sha256": canonical_sha256(probe),
                "algorithm_profile": "clothing-contact-screen-v1", "thresholds": deepcopy(THRESHOLDS),
                "reason_codes": list(WARNINGS) + ["heuristic_clothing_proxy_not_anatomy"],
                "relations": relations, "summary": summary}
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("benchmark_contact_screen_input_invalid") from exc


def validate_contact_screen(candidate, probe, document):
    expected = build_contact_screen(candidate, probe)
    if type(document) is not dict or expected != document or canonical_sha256(expected) != canonical_sha256(document):
        raise ValueError("benchmark_contact_screen_mismatch")
    return deepcopy(expected)
