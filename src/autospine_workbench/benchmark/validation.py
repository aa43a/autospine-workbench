"""Strict pending-annotation benchmark contract and portable asset paths."""
from collections import Counter
from copy import deepcopy
import re
import unicodedata

from ..manifest_artifacts import require_safe_token
from ..resolved_project import canonical_sha256

SCHEMA = "autospine.benchmark-manifest/v1"
SPLIT_COUNTS = {"development": 3, "visible": 4, "holdout": 3, "reserve": 10}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ASSET_FIELDS = {"path", "sha256", "byte_size", "canvas"}
_ANNOTATIONS = {"annotation_status": "pending", "complexity": None,
                "complexity_tags": [], "expected_core_layers": [],
                "reviewed_joints": {}, "supported_motion_set": [], "rights": None}


class BenchmarkError(ValueError):
    def __init__(self, reason_code="benchmark_manifest_invalid"):
        self.reason_code = reason_code
        super().__init__(reason_code)


def require_relative_asset_path(value, suffix):
    """Preserve Unicode source names while rejecting platform path aliases."""
    if type(value) is not str or not 1 <= len(value) <= 1024 or "\\" in value \
            or any(ord(char) < 32 for char in value) or ":" in value:
        raise BenchmarkError("benchmark_asset_path_invalid")
    parts = value.split("/")
    if any(not part or part in {".", ".."} or part.endswith((".", " ")) for part in parts):
        raise BenchmarkError("benchmark_asset_path_invalid")
    for part in parts:
        if any(char in part for char in '<>"|?*'):
            raise BenchmarkError("benchmark_asset_path_invalid")
        base = part.split(".", 1)[0].upper()
        if base in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9]", base):
            raise BenchmarkError("benchmark_asset_path_invalid")
    if not value.endswith(suffix):
        raise BenchmarkError("benchmark_asset_path_invalid")
    return value


def require_digest(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise BenchmarkError("benchmark_address_invalid")
    return value


def validate_asset(value, suffix):
    if type(value) is not dict or set(value) != _ASSET_FIELDS:
        raise BenchmarkError("benchmark_asset_invalid")
    require_relative_asset_path(value["path"], suffix)
    require_digest(value["sha256"])
    if type(value["byte_size"]) is not int or not 1 <= value["byte_size"] <= 1 << 40:
        raise BenchmarkError("benchmark_asset_invalid")
    canvas = value["canvas"]
    if type(canvas) is not list or len(canvas) != 2 or any(
        type(number) is not int or not 1 <= number <= 100000 for number in canvas
    ):
        raise BenchmarkError("benchmark_asset_invalid")


def validate_benchmark_manifest(document):
    try:
        _validate(document)
    except BenchmarkError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, OverflowError) as exc:
        raise BenchmarkError() from exc
    return deepcopy(document)


def _validate(document):
    if type(document) is not dict or set(document) != {
        "schema", "dataset_id", "source_inventory_sha256", "authority", "split_status", "characters",
    } or document["schema"] != SCHEMA or document["authority"] != "none":
        raise BenchmarkError()
    require_safe_token(document["dataset_id"], "Dataset id")
    require_digest(document["source_inventory_sha256"])
    if document["split_status"] not in {"unassigned", "frozen"}:
        raise BenchmarkError("benchmark_split_invalid")
    rows = document["characters"]
    if type(rows) is not list or len(rows) != 20:
        raise BenchmarkError("benchmark_character_count_invalid")
    paths, hashes, ids, split_counts, psd_count = set(), set(), [], Counter(), 0

    def observe(asset, suffix):
        validate_asset(asset, suffix)
        portable = unicodedata.normalize("NFKC", asset["path"]).casefold()
        if portable in paths or asset["sha256"] in hashes:
            raise BenchmarkError("benchmark_asset_duplicate")
        paths.add(portable)
        hashes.add(asset["sha256"])

    for row in rows:
        if type(row) is not dict or set(row) != {
            "id", "source", "psd_candidates", "dataset_split", *_ANNOTATIONS,
        }:
            raise BenchmarkError()
        observe(row["source"], ".png")
        expected_id = "character-" + row["source"]["sha256"][:16]
        if row["id"] != expected_id:
            raise BenchmarkError("benchmark_character_identity_invalid")
        ids.append(row["id"])
        if any(row[key] != value for key, value in _ANNOTATIONS.items()):
            raise BenchmarkError("benchmark_annotation_unsupported")
        split = row["dataset_split"]
        if split not in SPLIT_COUNTS and split != "unassigned":
            raise BenchmarkError("benchmark_split_invalid")
        split_counts[split] += 1
        candidates = row["psd_candidates"]
        if type(candidates) is not list or len(candidates) > 12:
            raise BenchmarkError("benchmark_psd_count_invalid")
        candidate_order = []
        for candidate in candidates:
            if type(candidate) is not dict or set(candidate) != {
                "source", "mapping", "variant_review_required", "dataset_split",
            }:
                raise BenchmarkError()
            observe(candidate["source"], ".psd")
            candidate_order.append(candidate["source"]["path"])
            if candidate["mapping"] != {
                "status": "candidate", "png_path": row["source"]["path"],
                "basis": "filename_transliteration_only", "requires_visual_review": True,
            } or type(candidate["mapping"].get("requires_visual_review")) is not bool:
                raise BenchmarkError("benchmark_mapping_not_candidate")
            if type(candidate["variant_review_required"]) is not bool:
                raise BenchmarkError("benchmark_mapping_not_candidate")
            if candidate["dataset_split"] != split:
                raise BenchmarkError("benchmark_variant_split_mismatch")
            psd_count += 1
        if candidate_order != sorted(candidate_order):
            raise BenchmarkError("benchmark_order_invalid")
    if psd_count != 12:
        raise BenchmarkError("benchmark_psd_count_invalid")
    if ids != sorted(set(ids)):
        raise BenchmarkError("benchmark_order_invalid")
    expected = {"unassigned": 20} if document["split_status"] == "unassigned" else SPLIT_COUNTS
    if dict(split_counts) != expected:
        raise BenchmarkError("benchmark_split_counts_invalid")
    canonical_sha256(document)
