"""Exact provenance for deterministic, explicitly mapped BVH MotionIR."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from . import bvh_motion_compiler as compiler_impl
from .bvh_map_validation import bvh_map_sha256, require_bvh_map
from .bvh_parser import parse_bvh
from .bvh_tokens import MAX_BVH_BYTES
from .motion_validation import motion_ir_sha256, require_motion_ir


FORMAT = "autospine-bvh-motion-compile-run"
FORMAT_VERSION = 1
MAX_RUN_BYTES = 32 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_TOP = {"format", "format_version", "source", "compiler", "output"}
_SOURCE = {
    "kind", "raw_bvh_sha256", "raw_bvh_byte_length",
    "bvh_map_sha256", "map_id", "clip_id",
}


class BvhMotionCompileRunError(ValueError):
    """Raised when BVH provenance is ambiguous or cannot rebuild its output."""


@dataclass(frozen=True, slots=True)
class BvhMotionCompileRun:
    """Frozen canonical run manifest with isolated document access."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_json(self) -> str:
        return self._canonical_json

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def raw_bvh_sha256(self) -> str:
        return self.document["source"]["raw_bvh_sha256"]

    @property
    def bvh_map_sha256(self) -> str:
        return self.document["source"]["bvh_map_sha256"]

    @property
    def motion_ir_sha256(self) -> str:
        return self.document["output"]["motion_ir_sha256"]


def build_bvh_motion_compile_run(
    raw_bvh: bytes,
    bvh_map: Mapping[str, Any],
    motion_ir: Mapping[str, Any],
) -> BvhMotionCompileRun:
    """Recompile exact inputs and issue provenance only for byte-identical output."""

    try:
        source, explicit_map, compiled = _compile_inputs(raw_bvh, bvh_map)
        _same_motion(motion_ir, compiled)
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "source": source,
            "compiler": {
                "id": compiler_impl.COMPILER_ID,
                "version": compiler_impl.COMPILER_VERSION,
                "config": compiler_impl.bvh_motion_compiler_config(),
            },
            "output": {"motion_ir_sha256": compiled.sha256},
        }
        require_bvh_motion_compile_run(document)
        return BvhMotionCompileRun(_canonical(document).decode("utf-8"))
    except BvhMotionCompileRunError:
        raise
    except (TypeError, ValueError) as exc:
        raise BvhMotionCompileRunError(
            f"BVH MotionIR compile-run generation failed: {exc}"
        ) from exc


def require_bvh_motion_compile_run(
    document: Mapping[str, Any],
    *,
    raw_bvh: bytes | None = None,
    bvh_map: Mapping[str, Any] | None = None,
    motion_ir: Mapping[str, Any] | None = None,
) -> None:
    """Validate the contract and optionally rebuild all source cross-bindings."""

    try:
        root = _object(document, "BVH compile run")
        _exact(root, _TOP, "BVH compile run")
        _identity(root)
        source = _source(root.get("source"))
        _compiler(root.get("compiler"))
        output = _output(root.get("output"))
        if (raw_bvh is None) != (bvh_map is None):
            raise BvhMotionCompileRunError(
                "raw BVH and BVH map cross-inputs must be supplied together"
            )
        compiled = None
        if raw_bvh is not None and bvh_map is not None:
            rebuilt_source, _, compiled = _compile_inputs(raw_bvh, bvh_map)
            if _canonical(rebuilt_source) != _canonical(source):
                raise BvhMotionCompileRunError(
                    "BVH compile-run source differs from exact cross-inputs"
                )
            if compiled.sha256 != output["motion_ir_sha256"]:
                raise BvhMotionCompileRunError(
                    "BVH compile-run output differs from rebuilt MotionIR"
                )
        if motion_ir is not None:
            if compiled is not None:
                _same_motion(motion_ir, compiled)
            elif motion_ir_sha256(motion_ir) != output["motion_ir_sha256"]:
                raise BvhMotionCompileRunError(
                    "MotionIR differs from the declared BVH output"
                )
        if len(_canonical(root)) > MAX_RUN_BYTES:
            raise BvhMotionCompileRunError(
                "BVH compile-run byte resource limit exceeded"
            )
    except BvhMotionCompileRunError:
        raise
    except (TypeError, ValueError) as exc:
        raise BvhMotionCompileRunError(
            f"BVH MotionIR compile-run validation failed: {exc}"
        ) from exc


def _compile_inputs(raw_bvh, bvh_map):
    parsed = parse_bvh(raw_bvh)
    explicit_map = _map_snapshot(bvh_map, parsed)
    compiled = compiler_impl.compile_bvh_motion(raw_bvh, explicit_map)
    source = {
        "kind": "bvh",
        "raw_bvh_sha256": parsed.source_sha256,
        "raw_bvh_byte_length": parsed.source_byte_length,
        "bvh_map_sha256": bvh_map_sha256(explicit_map),
        "map_id": explicit_map["map_id"],
        "clip_id": explicit_map["clip"]["clip_id"],
    }
    return source, explicit_map, compiled


def _map_snapshot(value, parsed):
    require_bvh_map(value, bvh=parsed)
    snapshot = json.loads(_canonical(value))
    require_bvh_map(snapshot, bvh=parsed)
    return snapshot


def _same_motion(motion_ir, compiled) -> None:
    require_motion_ir(motion_ir)
    if motion_ir_sha256(motion_ir) != compiled.sha256 \
            or _canonical(motion_ir) != compiled.canonical_bytes:
        raise BvhMotionCompileRunError(
            "MotionIR canonical bytes differ from the rebuilt BVH output"
        )


def _identity(root) -> None:
    if root.get("format") != FORMAT \
            or type(root.get("format_version")) is not int \
            or root.get("format_version") != FORMAT_VERSION:
        raise BvhMotionCompileRunError("BVH compile-run format is unsupported")


def _source(value):
    source = _object(value, "BVH compile-run source")
    _exact(source, _SOURCE, "BVH compile-run source")
    if source.get("kind") != "bvh":
        raise BvhMotionCompileRunError("BVH compile-run source kind is unsupported")
    for field in ("raw_bvh_sha256", "bvh_map_sha256"):
        if not isinstance(source.get(field), str) \
                or not _SHA256.fullmatch(source[field]):
            raise BvhMotionCompileRunError(f"BVH compile-run {field} is invalid")
    length = source.get("raw_bvh_byte_length")
    if type(length) is not int or not 1 <= length <= MAX_BVH_BYTES:
        raise BvhMotionCompileRunError("BVH compile-run source byte length is invalid")
    for field in ("map_id", "clip_id"):
        if not isinstance(source.get(field), str) \
                or not _SAFE_ID.fullmatch(source[field]):
            raise BvhMotionCompileRunError(f"BVH compile-run {field} is invalid")
    return source


def _compiler(value) -> None:
    compiler = _object(value, "BVH compile-run compiler")
    _exact(compiler, {"id", "version", "config"}, "BVH compile-run compiler")
    config = _object(compiler.get("config"), "BVH compile-run config")
    if compiler.get("id") != compiler_impl.COMPILER_ID \
            or compiler.get("version") != compiler_impl.COMPILER_VERSION \
            or _canonical(config) != _canonical(
                compiler_impl.bvh_motion_compiler_config()
            ):
        raise BvhMotionCompileRunError("BVH compile-run compiler identity drifted")


def _output(value):
    output = _object(value, "BVH compile-run output")
    _exact(output, {"motion_ir_sha256"}, "BVH compile-run output")
    digest = output.get("motion_ir_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise BvhMotionCompileRunError("BVH compile-run output SHA is invalid")
    return output


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BvhMotionCompileRunError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise BvhMotionCompileRunError(f"{label} fields are incomplete or unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
