"""Bounded, alias-safe immutable files for product orchestration journals."""

import json
import os
from pathlib import Path
import tempfile

from ..safe_input_files import read_real_file, strict_json_object
from ..spine42_v3_bundle_files import existing_exact_child, require_real_directory
from .pipeline_run import PipelineRunError

MAX_DOCUMENT_BYTES = 128 * 1024


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def directory(path, *, create=False):
    path = Path(os.path.abspath(os.fspath(path)))
    try:
        for current in reversed((path, *path.parents)):
            if current.parent == current:
                require_real_directory(current, "pipeline root")
                continue
            # Ancestors may be traversable without directory-list permission.
            # lstat validation rejects aliases without enumerating user homes.
            if not current.exists():
                if not create:
                    raise PipelineRunError("pipeline_run_not_found")
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
                if existing_exact_child(current.parent, current.name) is None:
                    raise PipelineRunError("pipeline_storage_invalid")
            require_real_directory(current, "pipeline directory")
        return path
    except PipelineRunError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise PipelineRunError("pipeline_storage_invalid") from exc


def read_document(path):
    try:
        directory(path.parent)
        exact = existing_exact_child(path.parent, path.name)
        if exact is None:
            raise PipelineRunError("pipeline_run_not_found")
        raw = read_real_file(exact, MAX_DOCUMENT_BYTES, "pipeline document")
        document = strict_json_object(raw, "pipeline document")
        if raw != canonical_bytes(document):
            raise PipelineRunError("pipeline_storage_invalid")
        return document
    except PipelineRunError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise PipelineRunError("pipeline_storage_invalid") from exc


def publish_document(path, value, *, staging):
    """Return False only when the exact destination already exists."""
    raw = canonical_bytes(value)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise PipelineRunError("pipeline_document_too_large")
    directory(path.parent)
    directory(staging, create=True)
    descriptor, name = tempfile.mkstemp(prefix="pending-", dir=staging)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if existing_exact_child(path.parent, path.name) is not None:
            return False
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        return True
    except (OSError, RuntimeError, ValueError) as exc:
        raise PipelineRunError("pipeline_storage_invalid") from exc
    finally:
        temporary.unlink(missing_ok=True)
