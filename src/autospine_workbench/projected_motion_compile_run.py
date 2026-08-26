"""Canonical provenance for one verified Kimodo-to-ProjectedMotion compile."""

from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .camera_model_validation import camera_model_sha256, require_camera_model
from . import kimodo_camera_projection as compiler_impl
from .motion_bundle_integrity import VerifiedMotionBundle
from .motion_validation import motion_ir_sha256, require_motion_ir
from .projected_motion_legacy import compile_projected_motion_to_motion_ir
from .projected_motion_validation import (
    projected_motion_ir_sha256, require_projected_motion_ir)
from .projected_motion_compile_run_validation import (
    ProjectedMotionCompileRunError, camera_row as _camera,
    canonical as _canonical, exact_fields as _exact, object_row as _object,
    output_row as _output, projection_metrics as _projection_metrics,
    require_compiler as _compiler, source_row as _source,
    validation_row as _validation,
)


FORMAT, FORMAT_VERSION = "autospine-projected-motion-compile-run", 1
MAX_RUN_BYTES = 64 * 1024
_TOP = {"format", "format_version", "source", "camera", "compiler",
        "validation", "output"}

@dataclass(frozen=True, slots=True)
class ProjectedMotionCompileRun:
    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def build_projected_motion_compile_run(
    bundle: VerifiedMotionBundle,
    camera: Mapping[str, Any],
    compiled: compiler_impl.CompiledProjectedMotion,
    legacy_motion: Mapping[str, Any],
) -> ProjectedMotionCompileRun:
    try:
        if type(bundle) is not VerifiedMotionBundle \
                or bundle.source_kind != "kimodo_npz":
            raise ProjectedMotionCompileRunError(
                "Projected compile run requires a verified Kimodo bundle"
            )
        if type(compiled) is not compiler_impl.CompiledProjectedMotion:
            raise ProjectedMotionCompileRunError(
                "Projected compile output is invalid"
            )
        projected = compiled.document
        require_projected_motion_ir(projected)
        require_camera_model(camera)
        require_motion_ir(legacy_motion)
        source = _expected_source(bundle)
        if _canonical(projected["source"]) != _canonical(source):
            raise ProjectedMotionCompileRunError(
                "Projected source differs from the verified motion bundle"
            )
        if projected["camera_sha256"] != camera_model_sha256(camera):
            raise ProjectedMotionCompileRunError(
                "Projected output differs from the supplied camera"
            )
        rebuilt_legacy = compile_projected_motion_to_motion_ir(projected)
        if _canonical(legacy_motion) != _canonical(rebuilt_legacy):
            raise ProjectedMotionCompileRunError(
                "Legacy MotionIR differs from the projected output"
            )
        validation = dict(compiled.consistency_metrics)
        validation.update(dict(compiled.projection_metrics))
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "source": source,
            "camera": {
                "camera_sha256": camera_model_sha256(camera),
                "camera_id": camera["camera_id"],
                "depth_positive": camera["depth_positive"],
            },
            "compiler": {
                "id": compiler_impl.COMPILER_ID,
                "version": compiler_impl.COMPILER_VERSION,
                "config": compiler_impl.projected_motion_compiler_config(),
            },
            "validation": validation,
            "output": {
                "projected_motion_ir_sha256": compiled.sha256,
                "legacy_motion_ir_sha256": motion_ir_sha256(legacy_motion),
            },
        }
        require_projected_motion_compile_run(
            document, camera=camera, projected_motion=projected,
            legacy_motion=legacy_motion,
        )
        return ProjectedMotionCompileRun(_canonical(document).decode("utf-8"))
    except ProjectedMotionCompileRunError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectedMotionCompileRunError(
            f"Projected compile-run generation failed: {exc}"
        ) from exc


def require_projected_motion_compile_run(
    document: Mapping[str, Any], *,
    camera: Mapping[str, Any] | None = None,
    projected_motion: Mapping[str, Any] | None = None,
    legacy_motion: Mapping[str, Any] | None = None,
) -> None:
    try:
        root = _object(document, "Projected compile run")
        _exact(root, _TOP, "Projected compile run")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise ProjectedMotionCompileRunError(
                "Projected compile-run format is unsupported"
            )
        source = _source(root.get("source"))
        camera_row = _camera(root.get("camera"))
        _compiler(root.get("compiler"))
        validation = _validation(root.get("validation"))
        output = _output(root.get("output"))
        if output["legacy_motion_ir_sha256"] != source["motion_ir_sha256"]:
            raise ProjectedMotionCompileRunError(
                "Projected legacy output differs from its P7 MotionIR source"
            )
        if camera is not None:
            require_camera_model(camera)
            expected = {"camera_sha256": camera_model_sha256(camera),
                        "camera_id": camera["camera_id"],
                        "depth_positive": camera["depth_positive"]}
            if _canonical(camera_row) != _canonical(expected):
                raise ProjectedMotionCompileRunError(
                    "Projected compile-run camera binding differs"
                )
        if projected_motion is not None:
            require_projected_motion_ir(projected_motion)
            if _canonical(projected_motion["source"]) != _canonical(source) \
                    or projected_motion["camera_sha256"] != \
                    camera_row["camera_sha256"] \
                    or projected_motion_ir_sha256(projected_motion) != \
                    output["projected_motion_ir_sha256"]:
                raise ProjectedMotionCompileRunError(
                    "ProjectedMotionIR differs from its compile-run binding"
                )
            metrics = _projection_metrics(projected_motion)
            if any(validation[field] != value for field, value in metrics.items()):
                raise ProjectedMotionCompileRunError(
                    "Projected validation metrics differ from the output"
                )
        if legacy_motion is not None:
            require_motion_ir(legacy_motion)
            if motion_ir_sha256(legacy_motion) != \
                    output["legacy_motion_ir_sha256"]:
                raise ProjectedMotionCompileRunError(
                    "Legacy MotionIR differs from its compile-run binding"
                )
            if projected_motion is not None and _canonical(legacy_motion) != \
                    _canonical(compile_projected_motion_to_motion_ir(
                        projected_motion
                    )):
                raise ProjectedMotionCompileRunError(
                    "Legacy MotionIR differs from the projected output"
                )
        if len(_canonical(root)) > MAX_RUN_BYTES:
            raise ProjectedMotionCompileRunError(
                "Projected compile-run byte limit exceeded"
            )
    except ProjectedMotionCompileRunError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise ProjectedMotionCompileRunError(
            f"Projected compile-run validation failed: {exc}"
        ) from exc


def _expected_source(bundle: VerifiedMotionBundle) -> dict[str, Any]:
    run_source = bundle.run_manifest.get("source")
    if not isinstance(run_source, Mapping):
        raise ProjectedMotionCompileRunError(
            "Verified Kimodo run source is unavailable"
        )
    return {"kind": "kimodo_npz", "motion_ir_sha256": bundle.clip_sha256,
            "motion_bundle_sha256": bundle.bundle_sha256,
            "motion_run_sha256": bundle.run_sha256,
            "raw_npz_sha256": run_source.get("raw_npz_sha256"),
            "source_sha256": run_source.get("source_sha256"),
            "map_sha256": run_source.get("map_sha256"),
            "array_inventory_sha256": run_source.get("array_inventory_sha256")}
