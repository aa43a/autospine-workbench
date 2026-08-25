"""Safe service boundary for compiling and verifying BVH MotionIR bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .bvh_map_validation import (
    MAX_DOCUMENT_BYTES as MAX_BVH_MAP_BYTES,
    BvhMapValidationError,
    bvh_map_sha256,
)
from .bvh_motion_compile_run import (
    BvhMotionCompileRunError,
    build_bvh_motion_compile_run,
)
from .bvh_motion_compiler import BvhMotionCompilerError, compile_bvh_motion
from .bvh_tokens import MAX_BVH_BYTES
from .motion_bundle_contract import BVH_DOCUMENT_NAMES, motion_bundle_address_sha256
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


class BvhMotionCommandError(RuntimeError):
    """Raised when a BVH command input or adjacent identity is not trustworthy."""


@dataclass(frozen=True, slots=True)
class BvhMotionBundleResult:
    """Frozen complete identity of one verified, explicitly mapped BVH bundle."""

    path: Path
    clip_id: str
    map_id: str
    raw_bvh_sha256: str
    raw_bvh_byte_length: int
    bvh_map_sha256: str
    motion_ir_sha256: str
    clip_sha256: str
    run_sha256: str
    bundle_sha256: str
    source_kind: str
    reused: bool | None


def compile_bvh_motion_bundle(
    state_root: Path,
    raw_bvh_path: Path,
    map_json_path: Path,
) -> BvhMotionBundleResult:
    """Read exact inputs once, compile, publish, and securely read back a bundle."""

    try:
        raw_bvh = read_real_file(raw_bvh_path, MAX_BVH_BYTES, "BVH source")
        bvh_map = strict_json_object(
            read_real_file(map_json_path, MAX_BVH_MAP_BYTES, "BVH map"),
            "BVH map",
        )
        compiled = compile_bvh_motion(raw_bvh, bvh_map)
        run = build_bvh_motion_compile_run(raw_bvh, bvh_map, compiled.document)
        expected_bytes = {
            "source.bvh": raw_bvh,
            "map.json": _canonical_json(bvh_map),
            "motion.json": compiled.canonical_bytes,
            "run-manifest.json": run.canonical_bytes,
        }
        published = MotionBundleStore(state_root).publish(
            compiled.document,
            run.document,
            raw_bvh=raw_bvh,
            bvh_map=bvh_map,
        )
        expected_bundle = motion_bundle_address_sha256(tuple(expected_bytes.items()))
        _require_publication(published, compiled, run, expected_bundle)
        verified = VerifiedMotionBundleReader(state_root).load(
            published.clip_sha256, published.bundle_sha256
        )
        for field in (
            "clip_id", "clip_sha256", "run_sha256", "bundle_sha256",
        ):
            if getattr(verified, field, None) != getattr(published, field, None):
                raise BvhMotionCommandError(
                    f"Verified BVH bundle {field} differs from publication"
                )
        if verified.path.resolve() != published.path.resolve():
            raise BvhMotionCommandError(
                "Verified BVH bundle path differs from publication"
            )
        return _result(verified, reused=published.reused, expected=expected_bytes)
    except BvhMotionCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise BvhMotionCommandError(f"BVH motion bundle compilation failed: {exc}") from exc


def verify_bvh_motion_bundle(
    state_root: Path,
    clip_sha256: str,
    bundle_sha256: str,
) -> BvhMotionBundleResult:
    """Securely rebuild one exact BVH address without discovering or writing state."""

    try:
        verified = VerifiedMotionBundleReader(state_root).load(
            clip_sha256, bundle_sha256
        )
        if verified.source_kind != "bvh":
            raise BvhMotionCommandError(
                "BVH verification rejects built-in motion bundles"
            )
        return _result(verified, reused=None)
    except BvhMotionCommandError:
        raise
    except _DOMAIN_ERRORS as exc:
        raise BvhMotionCommandError(f"BVH motion bundle verification failed: {exc}") from exc


def _require_publication(
    published: Any, compiled: Any, run: Any, bundle_sha256: str,
) -> None:
    expected = {
        "clip_id": compiled.document["clip_id"],
        "clip_sha256": compiled.sha256,
        "run_sha256": run.sha256,
        "bundle_sha256": bundle_sha256,
    }
    for field, value in expected.items():
        if getattr(published, field, None) != value:
            raise BvhMotionCommandError(
                f"Published BVH bundle {field} differs from compilation"
            )
    if type(getattr(published, "reused", None)) is not bool:
        raise BvhMotionCommandError("Published BVH bundle reuse status is invalid")
    if not isinstance(getattr(published, "path", None), Path):
        raise BvhMotionCommandError("Published BVH bundle path is invalid")


def _result(
    verified: Any,
    *,
    reused: bool | None,
    expected: dict[str, bytes] | None = None,
) -> BvhMotionBundleResult:
    if verified.source_kind != "bvh" or verified.inventory != BVH_DOCUMENT_NAMES:
        raise BvhMotionCommandError("Verified motion bundle source kind is not BVH")
    documents = verified.document_bytes
    if expected is not None and documents != expected:
        raise BvhMotionCommandError(
            "Verified BVH bundle bytes differ from the command snapshots"
        )
    raw_bvh, bvh_map = verified.raw_bvh, verified.bvh_map
    motion, run = verified.motion, verified.run_manifest
    source = run.get("source") if type(run) is dict else None
    output = run.get("output") if type(run) is dict else None
    if not all(type(value) is dict for value in (bvh_map, motion, source, output)):
        raise BvhMotionCommandError("Verified BVH bundle documents are incomplete")
    if type(raw_bvh) is not bytes or source.get("kind") != "bvh":
        raise BvhMotionCommandError("Verified BVH source snapshot is invalid")
    calculated = {
        "raw_bvh_sha256": hashlib.sha256(raw_bvh).hexdigest(),
        "raw_bvh_byte_length": len(raw_bvh),
        "bvh_map_sha256": bvh_map_sha256(bvh_map),
        "motion_ir_sha256": motion_ir_sha256(motion),
        "run_sha256": hashlib.sha256(documents["run-manifest.json"]).hexdigest(),
    }
    declared = {
        "raw_bvh_sha256": source.get("raw_bvh_sha256"),
        "raw_bvh_byte_length": source.get("raw_bvh_byte_length"),
        "bvh_map_sha256": source.get("bvh_map_sha256"),
        "motion_ir_sha256": output.get("motion_ir_sha256"),
        "run_sha256": verified.run_sha256,
    }
    if calculated != declared:
        raise BvhMotionCommandError("Verified BVH identities are not cross-bound")
    if (
        motion.get("clip_id") != verified.clip_id
        or source.get("clip_id") != verified.clip_id
        or source.get("map_id") != bvh_map.get("map_id")
        or calculated["motion_ir_sha256"] != verified.clip_sha256
        or reused is not None and type(reused) is not bool
        or not isinstance(verified.path, Path)
    ):
        raise BvhMotionCommandError("Verified BVH command identity differs from its bundle")
    return BvhMotionBundleResult(
        path=verified.path,
        clip_id=verified.clip_id,
        map_id=source["map_id"],
        raw_bvh_sha256=calculated["raw_bvh_sha256"],
        raw_bvh_byte_length=calculated["raw_bvh_byte_length"],
        bvh_map_sha256=calculated["bvh_map_sha256"],
        motion_ir_sha256=calculated["motion_ir_sha256"],
        clip_sha256=verified.clip_sha256,
        run_sha256=calculated["run_sha256"],
        bundle_sha256=verified.bundle_sha256,
        source_kind="bvh",
        reused=reused,
    )


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


_DOMAIN_ERRORS = (
    AttributeError,
    BvhMapValidationError,
    BvhMotionCompileRunError,
    BvhMotionCompilerError,
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
