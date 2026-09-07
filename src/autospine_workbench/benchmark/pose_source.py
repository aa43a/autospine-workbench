"""Source-bound pose ingestion without changing raw observations or authorizing them."""
import hashlib
import json
from pathlib import Path

from ..artifact_store import ImmutableJsonArtifactStore
from ..automation.storage_io import directory
from ..manifest_artifacts import require_safe_token, require_sha256
from ..pose_observations import MAX_POSE_DOCUMENT_BYTES, load_pose_observations
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file, strict_json_object
from ..spine42_v3_bundle_files import existing_exact_child

KIND = "benchmark-pose-observations"


def _context(candidate):
    if type(candidate) is not dict or candidate.get("schema") != "autospine.benchmark-semantic-candidates/v1" \
            or candidate.get("authority") != "none":
        raise ValueError("benchmark_pose_candidate_invalid")
    project_id = candidate.get("character_id")
    require_safe_token(project_id, "Benchmark character")
    digest = candidate.get("composite_sha256")
    require_sha256(digest, "Composite digest")
    canvas = candidate.get("canvas")
    if type(canvas) is not list or len(canvas) != 2 \
            or any(type(v) is not int or not 0 < v <= 65536 for v in canvas):
        raise ValueError("benchmark_pose_candidate_invalid")
    return {"expected_project_id": project_id, "expected_image_sha256": digest,
            "expected_canvas_size": tuple(canvas)}


def _folder(state_root, project_id, *, create=False):
    current = directory(Path(state_root), create=create)
    for name in ("analysis", project_id, KIND):
        found = existing_exact_child(current, name)
        if found is None and not create:
            raise ValueError("benchmark_pose_not_found")
        current = directory(current / name, create=create)
    return current


def _snapshot(path):
    parent = directory(path.parent)
    exact = existing_exact_child(parent, path.name)
    if exact is None or exact.lstat().st_nlink != 1:
        raise ValueError("benchmark_pose_source_invalid")
    raw = read_real_file(exact, MAX_POSE_DOCUMENT_BYTES, "benchmark pose")
    metadata = exact.lstat()
    if metadata.st_nlink != 1:
        raise ValueError("benchmark_pose_source_invalid")
    return raw, (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)


def _load(candidate, path, *, expected_digest=None):
    context = _context(candidate)
    path = Path(path).absolute()
    raw, before = _snapshot(path)
    document = strict_json_object(raw, "benchmark pose")
    if type(document.get("format_version")) is not int or document["format_version"] not in (1, 2):
        raise ValueError("benchmark_pose_format_invalid")
    digest = canonical_sha256(document)
    if expected_digest is not None and digest != expected_digest:
        raise ValueError("benchmark_pose_content_changed")
    loaded = load_pose_observations(path, **context)
    after_raw, after = _snapshot(path)
    if before != after or hashlib.sha256(raw).digest() != hashlib.sha256(after_raw).digest() \
            or loaded.document_sha256 != digest or canonical_sha256(loaded.document) != digest:
        raise ValueError("benchmark_pose_content_changed")
    return loaded


def ingest_pose(state_root, candidate, path):
    """Validate supplied pose v1/v2, preserve its document and read back publication."""
    try:
        loaded = _load(candidate, path)
        encoded = (json.dumps(loaded.document, ensure_ascii=False, allow_nan=False, indent=2,
                              sort_keys=True) + "\n").encode("utf-8")
        if len(encoded) > MAX_POSE_DOCUMENT_BYTES:
            raise ValueError("benchmark_pose_document_too_large")
        folder = _folder(state_root, loaded.project_id, create=True)
        existing = existing_exact_child(folder, loaded.document_sha256 + ".json")
        if existing is not None:
            _load(candidate, existing, expected_digest=loaded.document_sha256)
        published = ImmutableJsonArtifactStore(state_root).publish(KIND, loaded.project_id, loaded.document)
        if published.sha256 != loaded.document_sha256:
            raise ValueError("benchmark_pose_publication_changed")
        return read_pose(state_root, candidate, published.sha256)
    except (OSError, RuntimeError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        if type(exc) is ValueError and str(exc).startswith("benchmark_pose_"):
            raise
        raise ValueError("benchmark_pose_ingest_invalid") from exc


def read_pose(state_root, candidate, digest):
    """Exact-address reader revalidates source identity and the canonical pose contract."""
    try:
        context = _context(candidate)
        require_sha256(digest, "Pose digest")
        folder = _folder(state_root, context["expected_project_id"])
        path = existing_exact_child(folder, digest + ".json")
        if path is None:
            raise ValueError("benchmark_pose_not_found")
        return _load(candidate, path, expected_digest=digest)
    except (OSError, RuntimeError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        if type(exc) is ValueError and str(exc).startswith("benchmark_pose_"):
            raise
        raise ValueError("benchmark_pose_read_invalid") from exc
