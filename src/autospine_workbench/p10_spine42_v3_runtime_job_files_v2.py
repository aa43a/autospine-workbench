"""Alias-safe immutable JSON primitives for P10.7b v2 runtime jobs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

from .body_sway_visual_review_store_files import (
    BodySwayVisualReviewFilesError, exact_subdirectory,
    publish_named_document, read_named_document,
)
from .p10_spine42_v3_runtime_job_validation_v2 import SHA_PATTERN
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_bundle_files import Spine42BundleFilesError, require_real_directory

MAX_JOBS = 10_000
MAX_EVENTS = 10_000
MAX_DOCUMENT_BYTES = 128 * 1024
_EVENT_NAME = re.compile(r"^([0-9]{6})\.json$")


class P10Spine42V3RuntimeJobFilesV2Error(RuntimeError):
    pass


def normalized_state_root(value):
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(value))))
        return require_real_directory(absolute, "Runtime job v2 state root")
    except (OSError, TypeError, ValueError, Spine42BundleFilesError) as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 state root is unsafe") from exc


def namespace(root, name, *, create):
    try:
        jobs = exact_subdirectory(root, "jobs", create=create)
        return exact_subdirectory(jobs, name, create=create)
    except BodySwayVisualReviewFilesError as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 namespace is unsafe") from exc


def exact_directory(parent, name, *, create):
    try:
        return exact_subdirectory(parent, name, create=create)
    except BodySwayVisualReviewFilesError as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 directory is unsafe") from exc


def run_directory(root, namespace_name, job_id, *, create):
    require_sha(job_id)
    try:
        return exact_subdirectory(
            namespace(root, namespace_name, create=create),
            job_id, create=create,
        )
    except BodySwayVisualReviewFilesError as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 address is unavailable") from exc


def publish_json(parent, name, document, *, staging_parent=None):
    raw = canonical_bytes(document)
    if not 0 < len(raw) <= MAX_DOCUMENT_BYTES:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 document is excessive")
    try:
        publish_named_document(
            parent, name, raw, staging_parent=staging_parent or parent)
    except (BodySwayVisualReviewFilesError, OSError) as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 document cannot be published") from exc


def read_json(parent, name):
    try:
        raw = read_named_document(parent, name)
        if not 0 < len(raw) <= MAX_DOCUMENT_BYTES:
            raise P10Spine42V3RuntimeJobFilesV2Error(
                "Runtime job v2 document is excessive")
        document = strict_json_object(raw, "Runtime job v2 document")
        if canonical_bytes(document) != raw:
            raise P10Spine42V3RuntimeJobFilesV2Error(
                "Runtime job v2 document is not canonical")
        return document
    except P10Spine42V3RuntimeJobFilesV2Error:
        raise
    except (BodySwayVisualReviewFilesError, SafeInputFileError,
            OSError, TypeError, ValueError) as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 document is unsafe") from exc


def optional_json(parent, name):
    try:
        return read_json(parent, name)
    except P10Spine42V3RuntimeJobFilesV2Error as exc:
        try:
            matches = [item for item in parent.iterdir()
                       if item.name.casefold() == name.casefold()]
        except OSError:
            raise exc
        if not matches:
            return None
        raise exc


def event_inventory(directory):
    try:
        children = list(directory.iterdir())
        if len(children) > MAX_EVENTS:
            raise P10Spine42V3RuntimeJobFilesV2Error(
                "Runtime job v2 event inventory is excessive")
        found = {}
        for child in children:
            match = _EVENT_NAME.fullmatch(child.name)
            mode = child.lstat().st_mode
            if match is None or not stat.S_ISREG(mode) \
                    or _is_alias(child):
                raise P10Spine42V3RuntimeJobFilesV2Error(
                    "Runtime job v2 event inventory is unsafe")
            number = int(match.group(1))
            if number in found or event_name(number) != child.name:
                raise P10Spine42V3RuntimeJobFilesV2Error(
                    "Runtime job v2 event inventory is aliased")
            found[number] = child
        expected = list(range(1, len(found) + 1))
        if sorted(found) != expected:
            raise P10Spine42V3RuntimeJobFilesV2Error(
                "Runtime job v2 event inventory has a gap")
        return tuple((number, found[number]) for number in expected)
    except P10Spine42V3RuntimeJobFilesV2Error:
        raise
    except OSError as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 events cannot be enumerated") from exc


def require_inventory(directory, files, directories):
    expected = set(files) | set(directories)
    try:
        children = list(directory.iterdir())
        actual = {item.name for item in children}
        if len(children) != len(expected) or actual != expected \
                or len({name.casefold() for name in actual}) != len(actual):
            raise P10Spine42V3RuntimeJobFilesV2Error(
                "Runtime job v2 inventory is missing, extra, or wrong-case")
        for item in children:
            mode = item.lstat().st_mode
            wanted = stat.S_ISDIR(mode) if item.name in directories \
                else stat.S_ISREG(mode)
            if not wanted or _is_alias(item):
                raise P10Spine42V3RuntimeJobFilesV2Error(
                    "Runtime job v2 inventory contains an alias")
    except P10Spine42V3RuntimeJobFilesV2Error:
        raise
    except OSError as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 inventory cannot be inspected") from exc


def run_ids(root, namespace_name):
    family = namespace(root, namespace_name, create=True)
    try:
        children = list(family.iterdir())
        if len(children) > MAX_JOBS or any(
            SHA_PATTERN.fullmatch(item.name) is None
            or not stat.S_ISDIR(item.lstat().st_mode) or _is_alias(item)
            for item in children
        ):
            raise P10Spine42V3RuntimeJobFilesV2Error(
                "Runtime job v2 run inventory is unsafe")
        return tuple(sorted(item.name for item in children))
    except P10Spine42V3RuntimeJobFilesV2Error:
        raise
    except OSError as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 runs cannot be enumerated") from exc


def event_name(sequence):
    if type(sequence) is not int or not 1 <= sequence <= MAX_EVENTS:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 event sequence is invalid")
    return f"{sequence:06d}.json"


def require_sha(value):
    if type(value) is not str or SHA_PATTERN.fullmatch(value) is None:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 address is invalid")


def canonical_bytes(value):
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise P10Spine42V3RuntimeJobFilesV2Error(
            "Runtime job v2 document cannot be canonicalized") from exc


def _is_alias(path):
    metadata = path.lstat()
    junction = getattr(path, "is_junction", None)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or (
        callable(junction) and junction()
    ) or bool(getattr(metadata, "st_file_attributes", 0) & reparse)


__all__ = [
    "P10Spine42V3RuntimeJobFilesV2Error", "canonical_bytes",
    "event_inventory", "event_name", "exact_directory", "namespace",
    "normalized_state_root",
    "optional_json", "publish_json", "read_json", "require_inventory",
    "require_sha",
    "run_directory", "run_ids",
]
