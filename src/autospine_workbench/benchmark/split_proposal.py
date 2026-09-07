"""Reproducible engineering partition; no image or semantic approval."""

from ..resolved_project import canonical_sha256
from .validation import validate_benchmark_manifest


def propose_split(manifest, *, development_sources=()):
    validate_benchmark_manifest(manifest)
    if manifest["split_status"] != "unassigned":
        raise ValueError("benchmark_split_already_frozen")
    rows = manifest["characters"]
    requested = set(development_sources)
    forced = [row for row in rows if row["source"]["path"] in requested]
    if len(forced) != len(requested) or len(forced) > 3:
        raise ValueError("benchmark_development_sources_invalid")
    # Previously inspected samples belong to development, never held-out evaluation.
    eligible = [row for row in rows if row["psd_candidates"] or row in forced]
    if len(eligible) < 10:
        raise ValueError("benchmark_first_batch_insufficient")
    order = lambda row: row["source"]["sha256"]
    forced.sort(key=order)
    selected = forced + sorted((row for row in eligible if row not in forced), key=order)[:10 - len(forced)]
    assignment = {row["id"]: "reserve" for row in rows}
    for index, row in enumerate(selected):
        assignment[row["id"]] = "development" if index < 3 else "visible" if index < 7 else "holdout"
    return {"schema": "autospine.benchmark-split-proposal/v1", "authority": "none",
            "dataset_sha256": canonical_sha256(manifest),
            "method": "psd_available_then_source_sha256_v1",
            "development_sources": sorted(requested), "assignment": assignment,
            "limitations": ["Filename source mappings remain unreviewed candidates",
                            "First batch availability selection is not representative of all 20 images"]}
