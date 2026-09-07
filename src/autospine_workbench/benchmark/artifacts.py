"""Immutable benchmark reports and user-selected JSON exports."""

from pathlib import Path

from ..automation.storage_io import canonical_bytes, directory, publish_document, read_document
from ..manifest_artifacts import require_safe_token, require_sha256
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file, strict_json_object
from ..spine42_v3_bundle_files import existing_exact_child


def read_input(path):
    return strict_json_object(read_real_file(Path(path), 2 << 20, "benchmark JSON"), "benchmark JSON")


def publish_report(state_root, dataset_id, kind, document):
    require_safe_token(dataset_id, "Dataset id")
    require_safe_token(kind, "Report kind")
    if document.get("authority") != "none":
        raise ValueError("benchmark_report_authority_invalid")
    digest = canonical_sha256(document)
    root = _folder(state_root, dataset_id, kind, create=True)
    path = root / f"{digest}.json"
    publish_document(path, document, staging=root / "staging")
    if read_report(state_root, dataset_id, kind, digest) != document:
        raise ValueError("benchmark_report_storage_invalid")
    return digest


def read_report(state_root, dataset_id, kind, digest):
    require_safe_token(dataset_id, "Dataset id")
    require_safe_token(kind, "Report kind")
    require_sha256(digest, "Report digest")
    folder = _folder(state_root, dataset_id, kind)
    path = existing_exact_child(folder, f"{digest}.json")
    if path is None or path.lstat().st_nlink != 1:
        raise ValueError("benchmark_report_storage_invalid")
    document = read_document(path)
    if canonical_sha256(document) != digest or document.get("authority") != "none":
        raise ValueError("benchmark_report_storage_invalid")
    return document


def _folder(state_root, dataset_id, kind, *, create=False):
    current = directory(Path(state_root), create=create)
    for name in ("benchmarks", dataset_id, kind):
        found = existing_exact_child(current, name)
        if found is None and not create:
            raise ValueError("benchmark_report_not_found")
        current = directory(current / name, create=create)
    return current


def export_document(path, document):
    path = Path(path).absolute()
    root = directory(path.parent, create=True)
    created = publish_document(path, document, staging=root / ".benchmark-staging")
    if not created and read_real_file(path, 2 << 20, "benchmark output") != canonical_bytes(document):
        raise ValueError("benchmark_output_exists")
