"""Safe service boundary for compiling and verifying Kimodo MotionIR bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .kimodo_npz_compile_run import (
    KimodoNpzCompileRunError,
    build_kimodo_npz_compile_run,
)
from .kimodo_npz_compiler import (
    KimodoNpzCompilerError,
    compile_kimodo_npz_motion,
)
from .kimodo_npz_map_validation import (
    MAX_DOCUMENT_BYTES as MAX_KIMODO_MAP_BYTES,
    KimodoNpzMapError,
    kimodo_npz_map_sha256,
)
from .kimodo_npz_source import (
    MAX_RAW_NPZ_BYTES,
    MAX_SOURCE_DOCUMENT_BYTES,
    KimodoNpzSourceError,
    kimodo_npz_source_sha256,
)
from .motion_bundle_contract import (
    KIMODO_DOCUMENT_NAMES,
    motion_bundle_address_sha256,
)
from .motion_bundle_reader import (
    VerifiedMotionBundleReader,
    VerifiedMotionBundleReaderError,
)
from .motion_bundle_store import MotionBundleStore, MotionBundleStoreError
from .motion_validation import MotionValidationError, motion_ir_sha256
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)


_SHA256 = re.compile(r"[0-9a-f]{64}")


class KimodoMotionCommandError(RuntimeError):
    """Raised when command inputs or adjacent identities are not trustworthy."""


@dataclass(frozen=True, slots=True)
class KimodoMotionBundleResult:
    """Complete identity of one verified formal Kimodo motion bundle."""

    path: Path
    clip_id: str
    source_id: str
    map_id: str
    raw_npz_sha256: str
    raw_npz_byte_length: int
    source_sha256: str
    map_sha256: str
    array_inventory_sha256: str
    motion_ir_sha256: str
    clip_sha256: str
    run_sha256: str
    bundle_sha256: str
    source_kind: str
    reused: bool | None


def compile_kimodo_motion_bundle(
    state_root: Path,
    raw_npz_path: Path,
    source_json_path: Path,
    map_json_path: Path,
) -> KimodoMotionBundleResult:
    """Read exact files once, compile, publish, and securely read back."""

    try:
        raw_npz = read_real_file(
            raw_npz_path, MAX_RAW_NPZ_BYTES, "Kimodo NPZ source"
        )
        source = strict_json_object(
            read_real_file(
                source_json_path, MAX_SOURCE_DOCUMENT_BYTES,
                "Kimodo NPZ sidecar",
            ),
            "Kimodo NPZ sidecar",
        )
        mapping = strict_json_object(
            read_real_file(
                map_json_path, MAX_KIMODO_MAP_BYTES, "Kimodo NPZ map"
            ),
            "Kimodo NPZ map",
        )
        compiled = compile_kimodo_npz_motion(raw_npz, source, mapping)
        run = build_kimodo_npz_compile_run(
            raw_npz, source, mapping, compiled.document
        )
        expected = {
            "source.npz": raw_npz,
            "sidecar.json": _canonical_json(source),
            "map.json": _canonical_json(mapping),
            "motion.json": compiled.canonical_bytes,
            "run-manifest.json": run.canonical_bytes,
        }
        published = MotionBundleStore(state_root).publish(
            compiled.document, run.document,
            raw_npz=raw_npz, kimodo_source=source, kimodo_map=mapping,
        )
        expected_bundle = motion_bundle_address_sha256(tuple(expected.items()))
        _require_publication(published, compiled, run, expected_bundle)
        verified = VerifiedMotionBundleReader(state_root).load(
            published.clip_sha256, published.bundle_sha256
        )
        for field in ("clip_id", "clip_sha256", "run_sha256", "bundle_sha256"):
            if getattr(verified, field, None) != getattr(published, field, None):
                raise KimodoMotionCommandError(
                    f"Verified Kimodo bundle {field} differs from publication"
                )
        if verified.path.resolve() != published.path.resolve():
            raise KimodoMotionCommandError(
                "Verified Kimodo bundle path differs from publication"
            )
        return _result(verified, reused=published.reused, expected=expected)
    except KimodoMotionCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise KimodoMotionCommandError(
            f"Kimodo motion bundle compilation failed: {exc}"
        ) from exc


def verify_kimodo_motion_bundle(
    state_root: Path,
    clip_sha256: str,
    bundle_sha256: str,
) -> KimodoMotionBundleResult:
    """Rebuild one exact Kimodo address without discovering or writing state."""

    try:
        verified = VerifiedMotionBundleReader(state_root).load(
            clip_sha256, bundle_sha256
        )
        if verified.source_kind != "kimodo_npz":
            raise KimodoMotionCommandError(
                "Kimodo verification rejects non-Kimodo motion bundles"
            )
        return _result(verified, reused=None)
    except KimodoMotionCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise KimodoMotionCommandError(
            f"Kimodo motion bundle verification failed: {exc}"
        ) from exc


def _require_publication(published, compiled, run, bundle_sha256) -> None:
    expected = {
        "clip_id": compiled.document["clip_id"],
        "clip_sha256": compiled.sha256,
        "run_sha256": run.sha256,
        "bundle_sha256": bundle_sha256,
    }
    for field, value in expected.items():
        if getattr(published, field, None) != value:
            raise KimodoMotionCommandError(
                f"Published Kimodo bundle {field} differs from compilation"
            )
    if type(getattr(published, "reused", None)) is not bool \
            or not isinstance(getattr(published, "path", None), Path):
        raise KimodoMotionCommandError("Published Kimodo bundle result is invalid")


def _result(
    verified: Any,
    *,
    reused: bool | None,
    expected: dict[str, bytes] | None = None,
) -> KimodoMotionBundleResult:
    if verified.source_kind != "kimodo_npz" \
            or verified.inventory != KIMODO_DOCUMENT_NAMES:
        raise KimodoMotionCommandError(
            "Verified motion bundle source kind is not Kimodo NPZ"
        )
    documents = verified.document_bytes
    if expected is not None and documents != expected:
        raise KimodoMotionCommandError(
            "Verified Kimodo bundle bytes differ from command snapshots"
        )
    raw, source, mapping = (
        verified.raw_npz, verified.kimodo_source, verified.kimodo_map
    )
    motion, run = verified.motion, verified.run_manifest
    run_source = run.get("source") if type(run) is dict else None
    output = run.get("output") if type(run) is dict else None
    if type(raw) is not bytes or not all(
        type(value) is dict
        for value in (source, mapping, motion, run_source, output)
    ):
        raise KimodoMotionCommandError(
            "Verified Kimodo bundle documents are incomplete"
        )
    calculated = {
        "raw_npz_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_npz_byte_length": len(raw),
        "source_sha256": kimodo_npz_source_sha256(source),
        "map_sha256": kimodo_npz_map_sha256(mapping),
        "motion_ir_sha256": motion_ir_sha256(motion),
        "run_sha256": hashlib.sha256(documents["run-manifest.json"]).hexdigest(),
    }
    declared = {
        "raw_npz_sha256": run_source.get("raw_npz_sha256"),
        "raw_npz_byte_length": run_source.get("raw_npz_byte_length"),
        "source_sha256": run_source.get("source_sha256"),
        "map_sha256": run_source.get("map_sha256"),
        "motion_ir_sha256": output.get("motion_ir_sha256"),
        "run_sha256": verified.run_sha256,
    }
    inventory_sha = run_source.get("array_inventory_sha256")
    if calculated != declared or not isinstance(inventory_sha, str) \
            or not _SHA256.fullmatch(inventory_sha):
        raise KimodoMotionCommandError("Verified Kimodo identities are not cross-bound")
    if motion.get("clip_id") != verified.clip_id \
            or run_source.get("clip_id") != verified.clip_id \
            or run_source.get("source_id") != source.get("source_id") \
            or run_source.get("map_id") != mapping.get("map_id") \
            or calculated["motion_ir_sha256"] != verified.clip_sha256 \
            or reused is not None and type(reused) is not bool \
            or not isinstance(verified.path, Path):
        raise KimodoMotionCommandError(
            "Verified Kimodo command identity differs from its bundle"
        )
    return KimodoMotionBundleResult(
        path=verified.path,
        clip_id=verified.clip_id,
        source_id=source["source_id"],
        map_id=mapping["map_id"],
        raw_npz_sha256=calculated["raw_npz_sha256"],
        raw_npz_byte_length=calculated["raw_npz_byte_length"],
        source_sha256=calculated["source_sha256"],
        map_sha256=calculated["map_sha256"],
        array_inventory_sha256=inventory_sha,
        motion_ir_sha256=calculated["motion_ir_sha256"],
        clip_sha256=verified.clip_sha256,
        run_sha256=calculated["run_sha256"],
        bundle_sha256=verified.bundle_sha256,
        source_kind="kimodo_npz",
        reused=reused,
    )


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


_DOMAIN_ERRORS = (
    AttributeError,
    KimodoNpzCompileRunError,
    KimodoNpzCompilerError,
    KimodoNpzMapError,
    KimodoNpzSourceError,
    MotionBundleStoreError,
    VerifiedMotionBundleReaderError,
    MotionValidationError,
    KeyError,
    OSError,
    RecursionError,
    SafeInputFileError,
    TypeError,
    ValueError,
)
