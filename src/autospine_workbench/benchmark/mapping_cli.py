"""Verified development-only inputs for a self-contained coordinate review."""

import hashlib
import os
from pathlib import Path, PurePosixPath
import struct
import tempfile

from ..automation.storage_io import directory
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from ..spine42_v3_bundle_files import existing_exact_child
from .artifacts import export_document, publish_report, read_input
from .source_files import MAX_SOURCE_BYTES
from .validation import validate_benchmark_manifest


def register_parser(sub):
    cmd = sub.add_parser("mapping-review", help="Prepare a development PNG/PSD coordinate review")
    cmd.add_argument("--manifest", required=True, type=Path)
    cmd.add_argument("--evidence", required=True, type=Path)
    cmd.add_argument("--workspace", required=True, type=Path)
    cmd.add_argument("--character", required=True, help="Character id, PNG name, or PSD filename")
    cmd.add_argument("--html", required=True, type=Path)
    cmd.add_argument("--draft", type=Path)
    cmd.add_argument("--anchors", type=Path, help="Load a source-bound anchor draft downloaded from the page")
    cmd.add_argument("--calibration-output", type=Path)
    cmd.add_argument("--output", type=Path)


def prepare_review(manifest, evidence, workspace, selector, draft=None):
    from .mapping_view import render_mapping_review

    candidate, png, composite = load_review_inputs(manifest, evidence, workspace, selector, draft)
    return candidate, render_mapping_review(candidate, png, composite)


def load_review_inputs(manifest, evidence, workspace, selector, draft=None):
    from .mapping import build_mapping_candidate, validate_mapping_candidate

    validate_benchmark_manifest(manifest)
    if manifest["split_status"] != "frozen":
        raise ValueError("benchmark_frozen_split_required")
    pairs = [(row, psd) for row in manifest["characters"]
             if row["dataset_split"] == "development" for psd in row["psd_candidates"]
             if selector in {row["id"], PurePosixPath(row["source"]["path"]).stem, psd["source"]["path"]}]
    if len(pairs) != 1:
        raise ValueError("benchmark_mapping_selection_ambiguous_or_unavailable")
    row, psd = pairs[0]
    if type(evidence) is not dict or evidence.get("schema") != "autospine.development-audit-evidence/v1" \
            or evidence.get("authority") != "none" \
            or evidence.get("benchmark_manifest_sha256") != canonical_sha256(manifest) \
            or type(evidence.get("characters")) is not list \
            or any(type(item) is not dict for item in evidence["characters"]):
        raise ValueError("benchmark_mapping_evidence_mismatch")
    records = [item for item in evidence.get("characters", []) if item.get("character_id") == row["id"]
               and item.get("source_psd") == psd["source"]]
    if len(records) != 1 or records[0].get("source_png") != row["source"] \
            or records[0].get("dataset_split") != "development":
        raise ValueError("benchmark_mapping_evidence_mismatch")
    record = records[0]
    png = _read_asset(workspace, row["source"])
    psd_raw = _read_asset(workspace, psd["source"])
    composite_asset = record["outputs"]["composite"]
    composite = _read_asset(workspace, composite_asset)
    if _png_canvas(png) != row["source"]["canvas"] or _png_canvas(composite) != psd["source"]["canvas"]:
        raise ValueError("benchmark_mapping_canvas_mismatch")
    if len(psd_raw) < 22 or psd_raw[:6] != b"8BPS\x00\x01" \
            or list(reversed(struct.unpack(">II", psd_raw[14:22]))) != psd["source"]["canvas"]:
        raise ValueError("benchmark_mapping_canvas_mismatch")
    binding = {"audit_evidence_sha256": canonical_sha256(evidence),
               "composite_sha256": composite_asset["sha256"]}
    candidate = build_mapping_candidate(manifest, row["id"], psd["source"]["sha256"], evidence=binding)
    if draft is not None:
        validate_mapping_candidate(manifest, draft)
        if any(draft.get(key) != candidate.get(key) for key in candidate
               if key not in {"source_to_psd_transform", "basis"}):
            raise ValueError("benchmark_mapping_draft_mismatch")
        candidate = draft
    return candidate, png, composite


def _read_asset(workspace, asset):
    name = asset["path"]
    path = PurePosixPath(name)
    if not isinstance(name, str) or path.is_absolute() or "\\" in name or ":" in name \
            or any(part in {"", ".", ".."} for part in name.split("/")):
        raise ValueError("benchmark_mapping_path_invalid")
    raw = read_real_file(Path(workspace).joinpath(*path.parts), MAX_SOURCE_BYTES, "mapping source")
    if type(asset["byte_size"]) is not int or len(raw) != asset["byte_size"] \
            or hashlib.sha256(raw).hexdigest() != asset["sha256"]:
        raise ValueError("benchmark_mapping_source_changed")
    return raw


def _png_canvas(raw):
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("benchmark_mapping_image_invalid")
    return list(struct.unpack(">II", raw[16:24]))


def export_html(path, html):
    """Atomic, immutable UTF-8 export; a failed retry never replaces an old page."""
    path = Path(path).absolute()
    root = directory(path.parent, create=True)
    raw = html.encode("utf-8")
    if len(raw) > 64 << 20:
        raise ValueError("benchmark_mapping_page_too_large")
    if existing_exact_child(root, path.name) is not None:
        if read_real_file(path, 64 << 20, "mapping page") != raw:
            raise ValueError("benchmark_output_exists")
        return
    fd, name = tempfile.mkstemp(prefix="mapping-", dir=root)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if read_real_file(path, 64 << 20, "mapping page") != raw:
                raise ValueError("benchmark_output_exists")
    finally:
        temporary.unlink(missing_ok=True)


def execute(args):
    from .mapping import validate_mapping_candidate
    from .mapping_view import render_mapping_review

    if args.calibration_output and not args.anchors:
        raise ValueError("benchmark_mapping_anchors_required")
    manifest = read_input(args.manifest)
    candidate, png, composite = load_review_inputs(
        manifest, read_input(args.evidence), args.workspace, args.character,
        read_input(args.draft) if args.draft else None)
    report = None
    if args.anchors:
        from .mapping_anchors import fit_mapping_anchors

        anchors = read_input(args.anchors)
        report = fit_mapping_anchors(candidate, anchors)
        if report["fitted_candidate"] is not None:
            validate_mapping_candidate(manifest, report["fitted_candidate"])
        for kind, value in (("mapping-candidates", candidate), ("mapping-anchors", anchors),
                            ("mapping-calibrations", report)):
            publish_report(args.state_root, manifest["dataset_id"], kind, value)
        from .mapping_calibration_store import read_mapping_calibration

        read_mapping_calibration(args.state_root, manifest, canonical_sha256(report))
        if args.calibration_output:
            export_document(args.calibration_output, report)
        if report["fitted_candidate"] is not None:
            candidate = report["fitted_candidate"]
    html = render_mapping_review(candidate, png, composite, calibration=report)
    export_html(args.html, html)
    if report is not None and report["status"] == "blocked":
        return report, "mapping-calibrations", manifest["dataset_id"], 2
    return candidate, "mapping-candidates", manifest["dataset_id"], 0
