"""Isolated staging and atomic publication for P10.7b v2 job roots."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat

from .atomic_staging import create_same_parent_staging
from .motion_instance_v3_staging_cleanup import remove_lexical_staging
from .motion_instance_v3_staging_cleanup import is_alias
from .p10_spine42_v3_runtime_job_bindings_v2 import (
    require_runtime_job_retry_chain_v2,
)
from .p10_spine42_v3_runtime_job_contract_v2 import (
    P10Spine42V3RuntimeJobRequestV2,
)
from .p10_spine42_v3_runtime_job_files_v2 import namespace
from .p10_spine42_v3_runtime_job_files_v2 import require_inventory, read_json
from .spine42_v3_bundle_files import (
    Spine42V3BundleFilesError, existing_exact_child, require_real_directory,
    sync_directory,
)

STAGING_NAMESPACE = "body-sway-spine42-v3-runtime-job-staging-v2"
_NAME = re.compile(r"^\.[0-9a-f]{12}\.[A-Za-z0-9_-]{6,64}$")
_TEMP_NAME = re.compile(
    r"^\.[0-9a-f]{12}\.[A-Za-z0-9_-]{6,64}\.tmp$")
_MAX_STAGING_ENTRIES = 10_000


class P10Spine42V3RuntimeJobStagingV2Error(RuntimeError):
    pass


def create_runtime_job_staging_v2(root, job_id):
    try:
        parent = runtime_job_staging_parent_v2(root)
        staging = create_same_parent_staging(
            parent, prefix=f".{job_id[:12]}.")
        if staging.parent != parent or _NAME.fullmatch(staging.name) is None:
            raise P10Spine42V3RuntimeJobStagingV2Error(
                "Runtime job staging identity is invalid")
        return parent, require_real_directory(
            staging, "Runtime job v2 staging")
    except P10Spine42V3RuntimeJobStagingV2Error:
        raise
    except (OSError, RuntimeError, Spine42V3BundleFilesError) as exc:
        raise P10Spine42V3RuntimeJobStagingV2Error(
            "Runtime job staging cannot be created") from exc


def runtime_job_staging_parent_v2(root):
    return namespace(root, STAGING_NAMESPACE, create=True)


def runtime_job_staging_inventory_v2(root):
    """Return only exact real staging directories and known temp files."""
    try:
        parent = runtime_job_staging_parent_v2(root)
        children = list(parent.iterdir())
        if len(children) > _MAX_STAGING_ENTRIES:
            raise P10Spine42V3RuntimeJobStagingV2Error(
                "Runtime job staging inventory is excessive")
        directories, temporaries = [], []
        for child in children:
            mode = child.lstat().st_mode
            if _NAME.fullmatch(child.name) and stat.S_ISDIR(mode) \
                    and not is_alias(child):
                directories.append(child)
            elif _TEMP_NAME.fullmatch(child.name) and stat.S_ISREG(mode) \
                    and not is_alias(child):
                temporaries.append(child)
            else:
                raise P10Spine42V3RuntimeJobStagingV2Error(
                    "Runtime job staging inventory is unsafe")
        return parent, tuple(sorted(directories)), tuple(sorted(temporaries))
    except P10Spine42V3RuntimeJobStagingV2Error:
        raise
    except (OSError, RuntimeError, Spine42V3BundleFilesError) as exc:
        raise P10Spine42V3RuntimeJobStagingV2Error(
            "Runtime job staging inventory cannot be read") from exc


def cleanup_runtime_job_staging_temp_v2(path, parent):
    """Remove only one validated regular publish temporary."""
    if path.parent != parent or _TEMP_NAME.fullmatch(path.name) is None:
        return
    try:
        require_real_directory(parent, "Runtime job v2 staging parent")
        if stat.S_ISREG(path.lstat().st_mode) and not is_alias(path):
            path.unlink()
    except (OSError, RuntimeError, Spine42V3BundleFilesError):
        return


def recover_runtime_job_staging_v2(
    root, job_namespace, *, load_directory, load_predecessor, load_committed,
):
    """Commit only complete bound crash remnants; never execute their job."""
    parent, directories, temporaries = runtime_job_staging_inventory_v2(root)
    for temporary in temporaries:
        cleanup_runtime_job_staging_temp_v2(temporary, parent)
    for directory in directories:
        bound = False
        try:
            require_inventory(directory, {"request.json"}, {"events"})
            request = P10Spine42V3RuntimeJobRequestV2.from_document(
                read_json(directory, "request.json"))
            if not directory.name.startswith(f".{request.job_id[:12]}."):
                raise P10Spine42V3RuntimeJobStagingV2Error(
                    "Runtime job staging address differs")
            prepared = load_directory(directory, request.job_id, True)
            bound = True
            require_runtime_job_retry_chain_v2(prepared, load_predecessor)
            if len(prepared.events) != 1 or prepared.status != "queued":
                raise P10Spine42V3RuntimeJobStagingV2Error(
                    "Runtime job staging history is invalid")
        except (RuntimeError, TypeError, ValueError) as exc:
            if bound:
                raise P10Spine42V3RuntimeJobStagingV2Error(
                    "Bound runtime job staging is invalid") from exc
            cleanup_runtime_job_staging_v2(directory, parent)
            continue
        try:
            commit_runtime_job_staging_v2(
                root, job_namespace, request.job_id, directory)
            if load_committed(request.job_id).request != prepared.request:
                raise P10Spine42V3RuntimeJobStagingV2Error(
                    "Runtime job staged recovery differs")
        except (RuntimeError, TypeError, ValueError) as exc:
            raise P10Spine42V3RuntimeJobStagingV2Error(
                "Runtime job staging could not be recovered") from exc
        cleanup_runtime_job_staging_v2(directory, parent)


def existing_runtime_job_v2(root, job_namespace, job_id):
    try:
        parent = namespace(root, job_namespace, create=True)
        found = existing_exact_child(parent, job_id)
        return None if found is None else require_real_directory(
            found, "Runtime job v2 committed root")
    except (OSError, RuntimeError, Spine42V3BundleFilesError) as exc:
        raise P10Spine42V3RuntimeJobStagingV2Error(
            "Runtime job committed address is unsafe") from exc


def commit_runtime_job_staging_v2(
    root, job_namespace, job_id, staging,
):
    """Rename a complete sibling-staged tree; never replace a destination."""
    try:
        parent = namespace(root, job_namespace, create=True)
        existing = existing_exact_child(parent, job_id)
        if existing is not None:
            return require_real_directory(
                existing, "Runtime job v2 committed root"), True
        destination = parent / job_id
        os.rename(staging, destination)
        sync_directory(parent)
        return require_real_directory(
            destination, "Runtime job v2 committed root"), False
    except OSError as exc:
        try:
            existing = existing_exact_child(parent, job_id)
        except (OSError, RuntimeError, Spine42V3BundleFilesError):
            existing = None
        if existing is not None:
            return require_real_directory(
                existing, "Runtime job v2 committed root"), True
        raise P10Spine42V3RuntimeJobStagingV2Error(
            "Runtime job staging cannot be committed") from exc
    except (RuntimeError, Spine42V3BundleFilesError) as exc:
        raise P10Spine42V3RuntimeJobStagingV2Error(
            "Runtime job staging cannot be committed") from exc


def cleanup_runtime_job_staging_v2(staging, parent):
    """Remove only this validated staging child; never traverse an alias."""
    if staging is None or parent is None or staging.parent != parent \
            or _NAME.fullmatch(staging.name) is None:
        return
    try:
        require_real_directory(parent, "Runtime job v2 staging parent")
        remove_lexical_staging(staging, parent)
    except (NotImplementedError, OSError, RuntimeError,
            Spine42V3BundleFilesError):
        return


__all__ = [
    "P10Spine42V3RuntimeJobStagingV2Error", "STAGING_NAMESPACE",
    "cleanup_runtime_job_staging_temp_v2", "cleanup_runtime_job_staging_v2",
    "commit_runtime_job_staging_v2",
    "create_runtime_job_staging_v2", "existing_runtime_job_v2",
    "recover_runtime_job_staging_v2", "runtime_job_staging_inventory_v2",
    "runtime_job_staging_parent_v2",
]
