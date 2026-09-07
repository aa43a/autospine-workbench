"""Source-bound PNG to PSD mapping hypotheses; never annotation authority."""
from copy import deepcopy
import math

from ..resolved_project import canonical_sha256
from .validation import (
    BenchmarkError, SPLIT_COUNTS, require_digest, validate_asset, validate_benchmark_manifest,
)

SCHEMA = "autospine.benchmark-mapping-candidate/v1"
COORDINATE_SYSTEM = "pixel_top_left_y_down"
_FIELDS = {"schema", "dataset_sha256", "character_id", "dataset_split", "png_source",
           "psd_source", "source_to_psd_transform", "basis", "confidence",
           "review_required", "authority", "evidence"}


def _pair(value):
    if type(value) is not list or len(value) != 2 or any(
        type(number) not in {int, float} for number in value
    ):
        raise BenchmarkError("benchmark_mapping_transform_invalid")
    try:
        if not all(math.isfinite(number) for number in value):
            raise BenchmarkError("benchmark_mapping_transform_invalid")
    except OverflowError as exc:
        raise BenchmarkError("benchmark_mapping_transform_invalid") from exc
    return value


def validate_transform(transform):
    if type(transform) is not dict or set(transform) != {
        "scale", "translation", "coordinate_system",
    } or transform["coordinate_system"] != COORDINATE_SYSTEM:
        raise BenchmarkError("benchmark_mapping_transform_invalid")
    scale = _pair(transform["scale"])
    _pair(transform["translation"])
    if any(number == 0 for number in scale):
        raise BenchmarkError("benchmark_mapping_transform_singular")
    return deepcopy(transform)


def transform_point(transform, point, *, inverse=False):
    """Map continuous pixel coordinates, allowing explicit axis reflection."""
    transform = validate_transform(transform)
    point = _pair(point)
    scale, translation = transform["scale"], transform["translation"]
    try:
        result = [(number - offset) / factor if inverse else number * factor + offset
                  for number, factor, offset in zip(point, scale, translation)]
    except (OverflowError, ZeroDivisionError) as exc:
        raise BenchmarkError("benchmark_mapping_transform_invalid") from exc
    return list(_pair(result))


def inverse_transform_point(transform, point):
    return transform_point(transform, point, inverse=True)


def _resolve(manifest, character_id, psd_sha256, split):
    manifest = validate_benchmark_manifest(manifest)
    if manifest["split_status"] != "frozen":
        raise BenchmarkError("benchmark_mapping_split_not_frozen")
    if type(split) is not str or split not in SPLIT_COUNTS:
        raise BenchmarkError("benchmark_split_invalid")
    row = next((row for row in manifest["characters"] if row["id"] == character_id), None)
    if row is None:
        raise BenchmarkError("benchmark_mapping_character_unknown")
    if row["dataset_split"] != split:
        raise BenchmarkError("benchmark_mapping_split_mismatch")
    require_digest(psd_sha256)
    psd = next((candidate["source"] for candidate in row["psd_candidates"]
                if candidate["source"]["sha256"] == psd_sha256), None)
    if psd is None:
        raise BenchmarkError("benchmark_mapping_psd_mismatch")
    return manifest, row, psd


def build_mapping_candidate(manifest, character_id, psd_sha256, *, transform=None,
                            evidence=None, split="development"):
    manifest, row, psd = _resolve(manifest, character_id, psd_sha256, split)
    basis = "canvas_fit_hypothesis" if transform is None else "explicit_transform_draft"
    if transform is None:
        transform = {
            "scale": [target / source for target, source in zip(
                psd["canvas"], row["source"]["canvas"])],
            "translation": [0, 0], "coordinate_system": COORDINATE_SYSTEM,
        }
    document = {
        "schema": SCHEMA, "dataset_sha256": canonical_sha256(manifest),
        "character_id": character_id, "dataset_split": split,
        "png_source": deepcopy(row["source"]), "psd_source": deepcopy(psd),
        "source_to_psd_transform": deepcopy(transform), "basis": basis,
        "confidence": None, "review_required": True, "authority": "none",
        "evidence": deepcopy(evidence),
    }
    return validate_mapping_candidate(manifest, document, split=split)


def validate_mapping_candidate(manifest, candidate, *, split="development"):
    if type(candidate) is not dict or set(candidate) != _FIELDS \
            or candidate["schema"] != SCHEMA:
        raise BenchmarkError("benchmark_mapping_candidate_invalid")
    if candidate["authority"] != "none" or candidate["confidence"] is not None \
            or candidate["review_required"] is not True:
        raise BenchmarkError("benchmark_mapping_authority_invalid")
    if type(candidate["psd_source"]) is not dict:
        raise BenchmarkError("benchmark_mapping_source_mismatch")
    validate_asset(candidate["png_source"], ".png")
    validate_asset(candidate["psd_source"], ".psd")
    manifest, row, psd = _resolve(manifest, candidate["character_id"],
                                  candidate["psd_source"].get("sha256"), split)
    if candidate["dataset_sha256"] != canonical_sha256(manifest):
        raise BenchmarkError("benchmark_mapping_manifest_mismatch")
    if candidate["dataset_split"] != row["dataset_split"]:
        raise BenchmarkError("benchmark_mapping_split_mismatch")
    if candidate["png_source"] != row["source"] or candidate["psd_source"] != psd:
        raise BenchmarkError("benchmark_mapping_source_mismatch")
    transform = validate_transform(candidate["source_to_psd_transform"])
    if candidate["basis"] not in ("canvas_fit_hypothesis", "explicit_transform_draft"):
        raise BenchmarkError("benchmark_mapping_basis_invalid")
    if candidate["basis"] == "canvas_fit_hypothesis" and (
        transform["translation"] != [0, 0] or transform["scale"] != [
            target / source for target, source in zip(psd["canvas"], row["source"]["canvas"])]
    ):
        raise BenchmarkError("benchmark_mapping_basis_invalid")
    evidence = candidate["evidence"]
    if evidence is not None:
        if type(evidence) is not dict or set(evidence) != {
            "audit_evidence_sha256", "composite_sha256",
        }:
            raise BenchmarkError("benchmark_mapping_evidence_invalid")
        for digest in evidence.values():
            require_digest(digest)
    # Finite coefficients can still overflow on a canvas corner or its inverse.
    for canvas, inverse in ((row["source"]["canvas"], False), (psd["canvas"], True)):
        for x in (0, canvas[0]):
            for y in (0, canvas[1]):
                transform_point(transform, [x, y], inverse=inverse)
    canonical_sha256(candidate)
    return deepcopy(candidate)
