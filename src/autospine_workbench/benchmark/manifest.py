"""Import recorded source identities and explicitly freeze engineering splits."""
from copy import deepcopy

from ..resolved_project import canonical_sha256
from .validation import BenchmarkError, SCHEMA, _ANNOTATIONS, validate_benchmark_manifest


def import_inventory(inventory, *, dataset_id="touhou-20-v1"):
    """Copy only recorded identities; never promote alpha measurements to labels."""
    try:
        if type(inventory) is not dict or inventory.get("kind") != "autospine.benchmark-intake-inventory" \
                or type(inventory.get("format_version")) is not int or inventory["format_version"] != 1 \
                or inventory.get("authority") != "none" or inventory.get("annotation_status") != "pending" \
                or inventory.get("dataset_split") is not None:
            raise BenchmarkError("benchmark_inventory_invalid")
        inventory_sha = canonical_sha256(inventory)
        pngs, psds = inventory["png_assets"], inventory["psd_assets"]
        if type(pngs) is not list or len(pngs) != 20 or type(psds) is not list or len(psds) != 12:
            raise BenchmarkError("benchmark_inventory_counts_invalid")
        rows = {}
        for png in pngs:
            if png.get("annotation_status") != "pending" or png.get("dataset_split") is not None:
                raise BenchmarkError("benchmark_inventory_invalid")
            asset = _asset(png)
            if asset["path"] in rows:
                raise BenchmarkError("benchmark_asset_duplicate")
            rows[asset["path"]] = {
                "id": "character-" + asset["sha256"][:16], "source": asset,
                "psd_candidates": [], "dataset_split": "unassigned", **deepcopy(_ANNOTATIONS),
            }
        for psd in psds:
            mapping = deepcopy(psd["source_mapping"])
            source_path = mapping["png_path"]
            if source_path not in rows:
                raise BenchmarkError("benchmark_mapping_source_missing")
            rows[source_path]["psd_candidates"].append({
                "source": _asset(psd), "mapping": mapping,
                "variant_review_required": psd["variant_review_required"], "dataset_split": "unassigned",
            })
        for row in rows.values():
            row["psd_candidates"].sort(key=lambda candidate: candidate["source"]["path"])
        counts = inventory["counts"]
        if counts.get("png") != 20 or counts.get("new_psd") != 12 or counts.get("candidate_distinct_png_mappings") != sum(
            bool(row["psd_candidates"]) for row in rows.values()
        ):
            raise BenchmarkError("benchmark_inventory_counts_invalid")
        return validate_benchmark_manifest({
            "schema": SCHEMA, "dataset_id": dataset_id, "source_inventory_sha256": inventory_sha,
            "authority": "none", "split_status": "unassigned",
            "characters": sorted(rows.values(), key=lambda row: row["id"]),
        })
    except BenchmarkError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise BenchmarkError("benchmark_inventory_invalid") from exc


def _asset(row):
    return {key: deepcopy(row[key]) for key in ("path", "sha256", "byte_size", "canvas")}


def freeze_split(manifest, assignment):
    """Freeze an explicit 3/4/3/10 map; variants inherit their source allocation.

    This is engineering partitioning only, not approval of mappings or labels.
    An already frozen document can be replayed but cannot have its split changed.
    """
    document = validate_benchmark_manifest(manifest)
    if type(assignment) is not dict or set(assignment) != {row["id"] for row in document["characters"]}:
        raise BenchmarkError("benchmark_split_assignment_invalid")
    if document["split_status"] == "frozen":
        if assignment != {row["id"]: row["dataset_split"] for row in document["characters"]}:
            raise BenchmarkError("benchmark_split_frozen")
        return document
    for row in document["characters"]:
        row["dataset_split"] = assignment[row["id"]]
        for candidate in row["psd_candidates"]:
            candidate["dataset_split"] = row["dataset_split"]
    document["split_status"] = "frozen"
    return validate_benchmark_manifest(document)
