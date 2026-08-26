"""Exact provenance for deterministic formal Kimodo NPZ MotionIR."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any

from . import kimodo_npz_compiler as compiler_impl
from .kimodo_npz_consistency import (
    HEADING_NORM_TOLERANCE,
    MATRIX_CROSSCHECK_TOLERANCE,
    POSITION_CROSSCHECK_METERS,
)
from .kimodo_npz_map_validation import (
    kimodo_npz_map_sha256,
    require_kimodo_npz_map,
)
from .kimodo_npz_source import (
    MAX_RAW_NPZ_BYTES,
    kimodo_npz_source_sha256,
    require_kimodo_npz_source,
)
from .motion_validation import motion_ir_sha256, require_motion_ir


FORMAT = "autospine-kimodo-npz-motion-compile-run"
FORMAT_VERSION = 1
MAX_RUN_BYTES = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_TOP = {"format", "format_version", "source", "compiler", "validation", "output"}
_SOURCE = {
    "kind", "raw_npz_sha256", "raw_npz_byte_length", "source_sha256",
    "source_id", "map_sha256", "map_id", "clip_id",
    "array_inventory_sha256",
}
_VALIDATION = {
    "max_global_matrix_error", "max_heading_norm_error",
    "max_position_error_meters", "max_root_position_error_meters",
}


class KimodoNpzCompileRunError(ValueError):
    """Raised when formal Kimodo compile provenance cannot be reproduced."""


@dataclass(frozen=True, slots=True)
class KimodoNpzCompileRun:
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


def build_kimodo_npz_compile_run(
    raw_npz: bytes,
    source: Mapping[str, Any],
    mapping: Mapping[str, Any],
    motion_ir: Mapping[str, Any],
) -> KimodoNpzCompileRun:
    """Recompile every exact input before issuing a provenance manifest."""

    try:
        source_row, compiled = _compile_inputs(raw_npz, source, mapping)
        return _run_from_compiled(source_row, compiled, motion_ir)
    except KimodoNpzCompileRunError:
        raise
    except (TypeError, ValueError) as exc:
        raise KimodoNpzCompileRunError(
            f"Kimodo NPZ compile-run generation failed: {exc}"
        ) from exc


def compile_kimodo_npz_motion_run(
    raw_npz: bytes,
    source: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> tuple[compiler_impl.CompiledKimodoMotion, KimodoNpzCompileRun]:
    """Compile once and derive its exact run manifest from the same artifact."""

    try:
        source_row, compiled = _compile_inputs(raw_npz, source, mapping)
        run = _run_from_compiled(source_row, compiled, compiled.document)
        return compiled, run
    except KimodoNpzCompileRunError:
        raise
    except (TypeError, ValueError) as exc:
        raise KimodoNpzCompileRunError(
            f"Kimodo NPZ compile-run generation failed: {exc}"
        ) from exc


def require_kimodo_npz_compile_run(
    document: Mapping[str, Any],
    *,
    raw_npz: bytes | None = None,
    source: Mapping[str, Any] | None = None,
    mapping: Mapping[str, Any] | None = None,
    motion_ir: Mapping[str, Any] | None = None,
) -> None:
    """Validate and optionally rebuild all source/output cross-bindings."""

    try:
        root = _object(document, "Kimodo compile run")
        _exact(root, _TOP, "Kimodo compile run")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise KimodoNpzCompileRunError("Kimodo compile-run format is unsupported")
        source_row = _source(root.get("source"))
        _compiler(root.get("compiler"))
        validation = _validation(root.get("validation"))
        output = _output(root.get("output"))
        supplied = (raw_npz, source, mapping)
        if any(value is not None for value in supplied) \
                and not all(value is not None for value in supplied):
            raise KimodoNpzCompileRunError(
                "Kimodo raw NPZ, sidecar, and map must be supplied together"
            )
        compiled = None
        if raw_npz is not None and source is not None and mapping is not None:
            rebuilt_source, compiled = _compile_inputs(raw_npz, source, mapping)
            if _canonical(rebuilt_source) != _canonical(source_row) \
                    or _canonical(dict(compiled.consistency_metrics)) != \
                    _canonical(validation):
                raise KimodoNpzCompileRunError(
                    "Kimodo compile-run evidence differs from exact cross-inputs"
                )
            if compiled.sha256 != output["motion_ir_sha256"]:
                raise KimodoNpzCompileRunError(
                    "Kimodo compile-run output differs from rebuilt MotionIR"
                )
        if motion_ir is not None:
            if compiled is not None:
                _same_motion(motion_ir, compiled)
            elif motion_ir_sha256(motion_ir) != output["motion_ir_sha256"]:
                raise KimodoNpzCompileRunError(
                    "MotionIR differs from the declared Kimodo output"
                )
        if len(_canonical(root)) > MAX_RUN_BYTES:
            raise KimodoNpzCompileRunError("Kimodo compile-run byte limit exceeded")
    except KimodoNpzCompileRunError:
        raise
    except (TypeError, ValueError) as exc:
        raise KimodoNpzCompileRunError(
            f"Kimodo compile-run validation failed: {exc}"
        ) from exc


def _compile_inputs(raw_npz, source, mapping):
    require_kimodo_npz_source(source, raw_npz=raw_npz)
    require_kimodo_npz_map(mapping, source=source)
    compiled = compiler_impl.compile_kimodo_npz_motion(raw_npz, source, mapping)
    source_row = {
        "kind": "kimodo_npz",
        "raw_npz_sha256": hashlib.sha256(raw_npz).hexdigest(),
        "raw_npz_byte_length": len(raw_npz),
        "source_sha256": kimodo_npz_source_sha256(source),
        "source_id": source["source_id"],
        "map_sha256": kimodo_npz_map_sha256(mapping),
        "map_id": mapping["map_id"],
        "clip_id": mapping["clip"]["clip_id"],
        "array_inventory_sha256": compiled.array_inventory_sha256,
    }
    return source_row, compiled


def _run_from_compiled(source_row, compiled, motion_ir) -> KimodoNpzCompileRun:
    _same_motion(motion_ir, compiled)
    document = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "source": source_row,
        "compiler": {
            "id": compiler_impl.COMPILER_ID,
            "version": compiler_impl.COMPILER_VERSION,
            "config": compiler_impl.kimodo_npz_compiler_config(),
        },
        "validation": dict(compiled.consistency_metrics),
        "output": {"motion_ir_sha256": compiled.sha256},
    }
    require_kimodo_npz_compile_run(document)
    return KimodoNpzCompileRun(_canonical(document).decode("utf-8"))


def _same_motion(motion_ir, compiled) -> None:
    require_motion_ir(motion_ir)
    if motion_ir_sha256(motion_ir) != compiled.sha256 \
            or _canonical(motion_ir) != compiled.canonical_bytes:
        raise KimodoNpzCompileRunError(
            "MotionIR canonical bytes differ from rebuilt Kimodo output"
        )


def _source(value: Any) -> Mapping[str, Any]:
    source = _object(value, "Kimodo compile-run source")
    _exact(source, _SOURCE, "Kimodo compile-run source")
    if source.get("kind") != "kimodo_npz":
        raise KimodoNpzCompileRunError("Kimodo compile-run source kind is unsupported")
    for field in (
        "raw_npz_sha256", "source_sha256", "map_sha256",
        "array_inventory_sha256",
    ):
        value = source.get(field)
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise KimodoNpzCompileRunError(f"Kimodo compile-run {field} is invalid")
    length = source.get("raw_npz_byte_length")
    if type(length) is not int or not 1 <= length <= MAX_RAW_NPZ_BYTES:
        raise KimodoNpzCompileRunError("Kimodo compile-run byte length is invalid")
    for field in ("source_id", "map_id", "clip_id"):
        value = source.get(field)
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise KimodoNpzCompileRunError(f"Kimodo compile-run {field} is invalid")
    return source


def _compiler(value: Any) -> None:
    compiler = _object(value, "Kimodo compile-run compiler")
    _exact(compiler, {"id", "version", "config"}, "Kimodo compile-run compiler")
    config = _object(compiler.get("config"), "Kimodo compile-run config")
    if compiler.get("id") != compiler_impl.COMPILER_ID \
            or compiler.get("version") != compiler_impl.COMPILER_VERSION \
            or _canonical(config) != _canonical(
                compiler_impl.kimodo_npz_compiler_config()
            ):
        raise KimodoNpzCompileRunError("Kimodo compiler identity drifted")


def _validation(value: Any) -> Mapping[str, Any]:
    validation = _object(value, "Kimodo compile-run validation")
    _exact(validation, _VALIDATION, "Kimodo compile-run validation")
    limits = {
        "max_global_matrix_error": MATRIX_CROSSCHECK_TOLERANCE,
        "max_heading_norm_error": HEADING_NORM_TOLERANCE,
        "max_position_error_meters": POSITION_CROSSCHECK_METERS,
        "max_root_position_error_meters": POSITION_CROSSCHECK_METERS,
    }
    for field, maximum in limits.items():
        number = validation.get(field)
        if field == "max_heading_norm_error" and number is None:
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(number) or not 0 <= number <= maximum:
            raise KimodoNpzCompileRunError(
                f"Kimodo compile-run {field} is outside its validation bound"
            )
    return validation


def _output(value: Any) -> Mapping[str, Any]:
    output = _object(value, "Kimodo compile-run output")
    _exact(output, {"motion_ir_sha256"}, "Kimodo compile-run output")
    digest = output.get("motion_ir_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise KimodoNpzCompileRunError("Kimodo compile-run output SHA is invalid")
    return output


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KimodoNpzCompileRunError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise KimodoNpzCompileRunError(f"{label} fields are incomplete or unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
