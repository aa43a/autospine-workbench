"""Conservative PSD-name suggestions; no pixel inference or approval authority."""
from copy import deepcopy
import re
import unicodedata

from ..resolved_project import canonical_sha256
from .validation import (BenchmarkError, require_relative_asset_path, validate_asset,
                         validate_benchmark_manifest)

SCHEMA = "autospine.benchmark-semantic-candidates/v1"
VOCAB = (
    "body.face", "body.neck", "body.torso", "body.arm.upper", "body.arm.lower",
    "body.hand", "body.leg.upper", "body.leg.lower", "body.foot", "wear.top",
    "wear.sleeve", "wear.skirt", "wear.pants", "wear.shoe", "hair.front",
    "hair.side", "hair.back", "accessory.ribbon", "accessory.weapon",
)
VOCABULARY = VOCAB
_ALIASES = dict(zip(VOCAB, VOCAB))
_ALIASES.update({
    "face": "body.face", "neck": "body.neck", "torso": "body.torso",
    "upperarm": "body.arm.upper", "upper arm": "body.arm.upper",
    "forearm": "body.arm.lower", "lower arm": "body.arm.lower",
    "hand": "body.hand", "thigh": "body.leg.upper", "upper leg": "body.leg.upper",
    "calf": "body.leg.lower", "lower leg": "body.leg.lower", "foot": "body.foot",
    "topwear": "wear.top", "top": "wear.top", "sleeve": "wear.sleeve",
    "skirt": "wear.skirt", "pants": "wear.pants", "shoe": "wear.shoe",
    "front hair": "hair.front", "side hair": "hair.side", "back hair": "hair.back",
    "ribbon": "accessory.ribbon", "weapon": "accessory.weapon",
})
_AMBIGUOUS = {"arm", "leg", "handwear", "legwear", "bottomwear", "body", "hair"}


class SemanticCandidateError(BenchmarkError):
    """Stable reason codes for unsupported or inconsistent inputs."""


def _require(condition, reason="semantic_audit_invalid"):
    if not condition:
        raise SemanticCandidateError(reason)


def _sha(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)
    return value


def _file(value):
    _require(type(value) is dict and set(value) == {"path", "sha256", "byte_size"})
    _require(type(value["path"]) is str and bool(value["path"]))
    require_relative_asset_path(value["path"], ".png")
    _sha(value["sha256"])
    _require(type(value["byte_size"]) is int and value["byte_size"] > 0)
    return deepcopy(value)


def _layers(records, observations, canvas):
    _require(type(records) is list and 0 < len(records) <= 256)
    _require(type(observations) is list)
    pixels = [row for row in observations if type(row) is dict and row.get("kind") == "pixel"]
    _require(len(pixels) == len(records))
    result, traversals = [], set()
    for index, (row, observed) in enumerate(zip(records, pixels)):
        _require(type(row) is dict)
        _require(type(row.get("index")) is int and row["index"] == index)
        traversal = row["traversal_index"]
        _require(type(traversal) is int and traversal >= 0 and traversal not in traversals)
        traversals.add(traversal)
        name, bbox = row["name"], row["bbox"]
        _require(type(name) is str and 0 < len(name) <= 1000)
        _require(type(bbox) is list and len(bbox) == 4 and all(type(v) is int for v in bbox))
        _require(bbox[0] <= bbox[2] and bbox[1] <= bbox[3])
        for key in ("index", "traversal_index", "name", "bbox"):
            _require(type(observed.get(key)) is type(row[key]) and observed[key] == row[key]
                     and canonical_sha256(observed[key]) == canonical_sha256(row[key]),
                     "semantic_audit_layer_mismatch")
        empty, visible, count = observed["empty"], observed["visible"], observed["alpha_nonzero"]
        _require(type(empty) is bool and type(visible) is bool and type(count) is int)
        _require(0 <= count <= (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
        _require(empty == (count == 0))
        image = _file(row["image"])
        normalized = " ".join(unicodedata.normalize("NFKC", name).casefold().split())
        match = re.fullmatch(r"(.+)-([lr])", normalized)
        base, side = (match[1].strip(), match[2]) if match else (normalized, None)
        semantic = _ALIASES.get(base)
        reasons = ["exact_name_alias" if semantic else
                   "ambiguous_layer_name" if base in _AMBIGUOUS else "unmapped_layer_name"]
        if side:
            reasons.append("canonical_side_requires_review")
        if empty:
            reasons.append("empty_layer_review_required")
        if not visible:
            reasons.append("hidden_layer_review_required")
        if bbox[0] < 0 or bbox[1] < 0 or bbox[2] > canvas[0] or bbox[3] > canvas[1]:
            reasons.append("layer_outside_canvas")
        result.append({
            "layer_id": f"layer-{index:03d}", "index": index, "traversal_index": traversal,
            "name": name, "bbox": deepcopy(bbox), "image": image,
            "image_sha256": image["sha256"], "semantic": semantic, "raw_name_side": side,
            "canonical_side": "unknown", "observed": {"empty": empty, "visible": visible,
                                                       "alpha_nonzero": count},
            "confidence": None, "review_required": True, "reason_codes": reasons,
        })
    return result


def build_semantic_candidates(manifest, evidence, character_id, audit):
    """Caller verifies actual bytes; this core cross-checks recorded identities."""
    try:
        manifest = validate_benchmark_manifest(manifest)
        _require(manifest["split_status"] == "frozen", "semantic_split_not_frozen")
        rows = [r for r in manifest["characters"] if r["id"] == character_id]
        _require(len(rows) == 1, "semantic_character_unknown")
        row = rows[0]
        _require(row["dataset_split"] == "development", "semantic_development_only")
        _require(evidence["schema"] == "autospine.development-audit-evidence/v1")
        _require(evidence["authority"] == "none" and evidence["scope"] == "development_only")
        _require(evidence["dataset_id"] == manifest["dataset_id"])
        manifest_sha = canonical_sha256(manifest)
        _require(evidence["benchmark_manifest_sha256"] == manifest_sha, "semantic_manifest_mismatch")
        matches = [r for r in evidence["characters"] if r["character_id"] == character_id]
        _require(len(matches) == 1, "semantic_evidence_character_ambiguous")
        record = matches[0]
        _require(record["dataset_split"] == "development" and record["authority"] == "none")
        validate_asset(record["source_png"], ".png")
        validate_asset(record["source_psd"], ".psd")
        _require(record["source_png"] == row["source"], "semantic_source_mismatch")
        _require(record["source_psd"] in [p["source"] for p in row["psd_candidates"]],
                 "semantic_source_mismatch")
        psd, canvas = record["source_psd"], record["canvas"]
        _require(canvas == psd["canvas"] and audit["canvas"] == canvas)
        _require(audit["sha256"] == psd["sha256"] and audit["file_size"] == psd["byte_size"],
                 "semantic_source_mismatch")
        layers = _layers(record["outputs"]["layers"], audit["layers"], canvas)
        _require(record["pixel_layers"] == len(layers) and audit["pixel_layers"] == len(layers))
        return {
            "schema": SCHEMA, "dataset_id": manifest["dataset_id"], "character_id": character_id,
            "benchmark_manifest_sha256": manifest_sha, "evidence_sha256": canonical_sha256(evidence),
            "audit_snapshot_sha256": canonical_sha256(audit),
            "audit_envelope_sha256": canonical_sha256({
                "schema": "autospine.benchmark-audit-snapshot/v1", "authority": "none", "payload": audit}),
            "source_png_sha256": row["source"]["sha256"], "source_psd_sha256": psd["sha256"],
            "composite_sha256": _sha(record["outputs"]["composite"]["sha256"]),
            "canvas": deepcopy(canvas), "algorithm_profile": "exact-layer-name-v1",
            "authority": "none", "coordinate_system": "psd_canvas", "review_required": True,
            "layers": layers,
        }
    except SemanticCandidateError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise SemanticCandidateError("semantic_audit_invalid") from exc


def validate_semantic_candidates(manifest, evidence, document, audit):
    """Reject altered suggestions and fields by deterministic full recomputation."""
    _require(type(document) is dict, "semantic_candidate_invalid")
    expected = build_semantic_candidates(manifest, evidence, document.get("character_id"), audit)
    _require(document == expected and canonical_sha256(document) == canonical_sha256(expected),
             "semantic_candidate_mismatch")
    return deepcopy(expected)
