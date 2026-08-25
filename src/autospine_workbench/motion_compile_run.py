"""Exact provenance contract for deterministic built-in MotionIR generation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .motion_builtin import (
    SUPPORTED_BUILTIN_CLIPS,
    BuiltinMotionError,
    build_builtin_motion,
)
from .motion_validation import (
    MotionValidationError,
    motion_ir_sha256,
    require_motion_ir,
)


FORMAT = "autospine-motion-compile-run"
FORMAT_VERSION = 1
COMPILER_ID = "builtin-motion-generator"
COMPILER_VERSION = "1.0.0"
BUILTIN_PROFILE = "autospine-builtins-v1"
MAX_RUN_BYTES = 16 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TOP_FIELDS = {"format", "format_version", "source", "compiler", "output"}


class MotionCompileRunError(ValueError):
    """Raised when built-in provenance cannot reproduce its exact MotionIR."""


@dataclass(frozen=True, slots=True)
class MotionCompileRun:
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
    def builtin_id(self) -> str:
        return self.document["source"]["builtin_id"]

    @property
    def motion_ir_sha256(self) -> str:
        return self.document["output"]["motion_ir_sha256"]


def build_builtin_motion_compile_run(
    builtin_id: str,
    motion_ir: Mapping[str, Any],
) -> MotionCompileRun:
    """Rebuild a built-in and issue provenance only for byte-equivalent MotionIR."""

    try:
        expected = _expected_builtin(builtin_id)
        _require_same_motion(motion_ir, expected)
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "source": {"kind": "builtin", "builtin_id": builtin_id},
            "compiler": {
                "id": COMPILER_ID,
                "version": COMPILER_VERSION,
                "config": {"profile": BUILTIN_PROFILE},
            },
            "output": {"motion_ir_sha256": expected.sha256},
        }
        require_motion_compile_run(document, motion_ir=motion_ir)
        encoded = _canonical(document)
        return MotionCompileRun(encoded.decode("utf-8"))
    except MotionCompileRunError:
        raise
    except (BuiltinMotionError, MotionValidationError, TypeError, ValueError) as exc:
        raise MotionCompileRunError(
            f"Built-in MotionIR compile-run generation failed: {exc}"
        ) from exc


def require_motion_compile_run(
    document: Mapping[str, Any],
    *,
    motion_ir: Mapping[str, Any] | None = None,
) -> None:
    """Validate exact compiler identity and reproduce the declared built-in output."""

    try:
        root = _object(document, "Motion compile run")
        _exact(root, _TOP_FIELDS, "Motion compile run")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise MotionCompileRunError("Motion compile-run format is unsupported")
        source = _object(root.get("source"), "Motion compile-run source")
        _exact(source, {"kind", "builtin_id"}, "Motion compile-run source")
        builtin_id = source.get("builtin_id")
        if source.get("kind") != "builtin" or builtin_id not in SUPPORTED_BUILTIN_CLIPS:
            raise MotionCompileRunError("Motion compile-run built-in source is unsupported")
        compiler = _object(root.get("compiler"), "Motion compile-run compiler")
        _exact(compiler, {"id", "version", "config"}, "Motion compile-run compiler")
        config = _object(compiler.get("config"), "Motion compile-run config")
        _exact(config, {"profile"}, "Motion compile-run config")
        if compiler.get("id") != COMPILER_ID \
                or compiler.get("version") != COMPILER_VERSION \
                or config.get("profile") != BUILTIN_PROFILE:
            raise MotionCompileRunError("Motion compile-run compiler identity drifted")
        output = _object(root.get("output"), "Motion compile-run output")
        _exact(output, {"motion_ir_sha256"}, "Motion compile-run output")
        digest = output.get("motion_ir_sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise MotionCompileRunError("Motion compile-run output SHA is invalid")
        expected = _expected_builtin(str(builtin_id))
        if digest != expected.sha256:
            raise MotionCompileRunError("Motion compile-run output differs from rebuilt built-in")
        if motion_ir is not None:
            _require_same_motion(motion_ir, expected)
        if len(_canonical(root)) > MAX_RUN_BYTES:
            raise MotionCompileRunError("Motion compile-run byte resource limit exceeded")
    except MotionCompileRunError:
        raise
    except (BuiltinMotionError, MotionValidationError, TypeError, ValueError) as exc:
        raise MotionCompileRunError(f"Motion compile-run validation failed: {exc}") from exc


def _expected_builtin(builtin_id: Any):
    if type(builtin_id) is not str or builtin_id not in SUPPORTED_BUILTIN_CLIPS:
        raise MotionCompileRunError("Motion compile-run built-in id is unsupported")
    return build_builtin_motion(builtin_id)


def _require_same_motion(motion_ir: Mapping[str, Any], expected) -> None:
    require_motion_ir(motion_ir)
    if motion_ir_sha256(motion_ir) != expected.sha256 \
            or _canonical(motion_ir) != expected.canonical_json.encode("utf-8"):
        raise MotionCompileRunError("MotionIR differs from the rebuilt built-in source")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MotionCompileRunError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise MotionCompileRunError(f"{label} fields are incomplete or unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
