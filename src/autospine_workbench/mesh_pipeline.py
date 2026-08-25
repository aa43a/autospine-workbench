"""Pure in-memory orchestration for exact, reviewed P3 mesh evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .mesh_eligibility import HingeTarget
from .mesh_probe_report import build_mesh_probe_report
from .mesh_visual_artifacts import build_mesh_visual_artifacts
from .png_rgba import RgbaImage
from .resolved_project import canonical_sha256
from .verified_mesh_compiler import VerifiedMeshCompiler


_TARGET_FIELDS = frozenset({"attachment_id", "source_layer_id", "side",
                            "proximal_bone_id", "distal_bone_id"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class VerifiedMeshPipelineError(RuntimeError):
    """Raised when an exact in-memory P3 build cannot be completed atomically."""


@dataclass(frozen=True, slots=True)
class VerifiedMeshPipelineResult:
    """Frozen canonical documents, evidence PNGs, and their complete identities."""

    project_id: str
    summary: str
    _rig_json: str = field(repr=False)
    _run_json: str = field(repr=False)
    _probes_json: str = field(repr=False)
    _visuals_json: str = field(repr=False)
    _png_items: tuple[tuple[str, bytes], ...] = field(repr=False)
    _input_sha_json: str = field(repr=False)
    _output_sha_json: str = field(repr=False)

    @property
    def rig(self) -> dict[str, Any]:
        return json.loads(self._rig_json)
    @property
    def run_manifest(self) -> dict[str, Any]:
        return json.loads(self._run_json)
    @property
    def probes(self) -> dict[str, Any]:
        return json.loads(self._probes_json)
    @property
    def visuals(self) -> dict[str, Any]:
        return json.loads(self._visuals_json)
    @property
    def pngs(self) -> dict[str, bytes]:
        return dict(self._png_items)
    @property
    def input_sha256s(self) -> dict[str, Any]:
        return json.loads(self._input_sha_json)
    @property
    def output_sha256s(self) -> dict[str, Any]:
        return json.loads(self._output_sha_json)


@dataclass(frozen=True, slots=True)
class VerifiedMeshPipeline:
    """Build exact P3 documents and visuals without aliases or filesystem writes."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def build(
        self,
        project_id: str,
        base_rig_sha256: str,
        base_bundle_sha256: str,
    ) -> VerifiedMeshPipelineResult:
        """Run compile, probe, and visual gates as one fail-closed memory build."""
        try:
            _identity(project_id, "project id", _SAFE_ID)
            _identity(base_rig_sha256, "base RigIR SHA", _SHA256)
            _identity(base_bundle_sha256, "base bundle SHA", _SHA256)
            compiled = VerifiedMeshCompiler(self.state_root).compile(
                project_id, base_rig_sha256, base_bundle_sha256
            )
            _compiler_identity(
                compiled, project_id, base_rig_sha256, base_bundle_sha256
            )
            rig, run = compiled.rig, compiled.run_manifest
            targets = _targets(compiled.targets)
            expected_summary = f"converted={len(targets)}" if targets else "reviewed-noop"
            probes = build_mesh_probe_report(rig, run, targets).document
            if not isinstance(probes, Mapping) or probes.get("status") != "passed":
                raise VerifiedMeshPipelineError(
                    "Verified mesh probes did not pass; visuals were not generated")
            if probes.get("summary") != expected_summary:
                raise VerifiedMeshPipelineError("Mesh probe summary is inconsistent")

            images = _images(compiled.target_images, targets)
            source_pngs = _pngs(compiled.target_png_bytes, targets, "target PNG")
            visuals_result = build_mesh_visual_artifacts(
                rig, run, probes, targets, images)
            visuals = visuals_result.document
            pngs = _pngs(visuals_result.png_by_path, None, "visual PNG")
            if (
                not isinstance(visuals, Mapping)
                or visuals.get("status") != "passed"
                or visuals.get("summary") != expected_summary
                or compiled.status != expected_summary
            ):
                raise VerifiedMeshPipelineError(
                    "Mesh compilation, probes, and visuals disagree")
            input_shas = _input_shas(compiled, run, images, source_pngs)
            output_shas = {
                "rig_sha256": canonical_sha256(rig),
                "run_manifest_sha256": canonical_sha256(run),
                "probes_sha256": canonical_sha256(probes),
                "visuals_sha256": canonical_sha256(visuals),
                "png_sha256_by_path": {
                    path: _bytes_sha(data) for path, data in sorted(pngs.items())
                },
            }
            return VerifiedMeshPipelineResult(
                project_id=project_id,
                summary=expected_summary,
                _rig_json=_encode(rig),
                _run_json=_encode(run),
                _probes_json=_encode(probes),
                _visuals_json=_encode(visuals),
                _png_items=tuple(sorted(pngs.items())),
                _input_sha_json=_encode(input_shas),
                _output_sha_json=_encode(output_shas),
            )
        except VerifiedMeshPipelineError:
            raise
        except (RuntimeError, TypeError, ValueError, KeyError, OverflowError) as exc:
            raise VerifiedMeshPipelineError(
                f"Verified mesh pipeline failed: {exc}"
            ) from exc


def _targets(value: Any) -> tuple[HingeTarget, ...]:
    if not isinstance(value, list):
        raise VerifiedMeshPipelineError("Compiler targets must be a JSON array")
    result, attachments, sources = [], set(), set()
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != _TARGET_FIELDS:
            raise VerifiedMeshPipelineError(
                "Compiler target must contain exactly five fields"
            )
        values = {key: _identity(raw.get(key), key, _SAFE_ID) for key in _TARGET_FIELDS}
        side = values["side"]
        if (
            side not in {"left", "right"}
            or values["proximal_bone_id"] != f"thigh.{side}"
            or values["distal_bone_id"] != f"calf.{side}"
            or values["attachment_id"] != values["source_layer_id"]
        ):
            raise VerifiedMeshPipelineError("Compiler target differs from profile-v1")
        attachment_key = values["attachment_id"].casefold()
        source_key = values["source_layer_id"].casefold()
        if attachment_key in attachments or source_key in sources:
            raise VerifiedMeshPipelineError("Compiler targets are duplicated")
        attachments.add(attachment_key)
        sources.add(source_key)
        result.append(HingeTarget(**values))
    return tuple(sorted(result, key=lambda item: item.attachment_id))


def _compiler_identity(compiled, project, rig_sha, bundle_sha) -> None:
    values = (
        (compiled.project_id, project, "project"),
        (compiled.base_rig_sha256, rig_sha, "base RigIR"),
        (compiled.base_bundle_sha256, bundle_sha, "base bundle"),
    )
    if any(actual != expected for actual, expected, _ in values):
        raise VerifiedMeshPipelineError("Compiler identity differs from the request")
    _identity(compiled.manifest_sha256, "layer manifest SHA", _SHA256)


def _images(value, targets) -> dict[str, RgbaImage]:
    expected = {item.attachment_id for item in targets}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise VerifiedMeshPipelineError("Target image keys differ from targets")
    if any(not isinstance(image, RgbaImage) for image in value.values()):
        raise VerifiedMeshPipelineError("Target images must be RGBA snapshots")
    return dict(value)


def _pngs(value, targets, label) -> dict[str, bytes]:
    if not isinstance(value, Mapping):
        raise VerifiedMeshPipelineError(f"{label} map is invalid")
    if targets is not None and set(value) != {item.attachment_id for item in targets}:
        raise VerifiedMeshPipelineError(f"{label} keys differ from targets")
    if any(not isinstance(key, str) or not isinstance(data, bytes)
           for key, data in value.items()):
        raise VerifiedMeshPipelineError(f"{label} map is invalid")
    return dict(value)


def _input_shas(compiled, run, images, source_pngs) -> dict[str, Any]:
    inputs = run.get("inputs") if isinstance(run, Mapping) else None
    expected = {
        "base_rig_sha256": compiled.base_rig_sha256,
        "base_bundle_sha256": compiled.base_bundle_sha256,
        "layer_manifest_sha256": compiled.manifest_sha256,
    }
    if not isinstance(inputs, Mapping) or any(inputs.get(k) != v for k, v in expected.items()):
        raise VerifiedMeshPipelineError("Compile-run input identity is inconsistent")
    resolved = _identity(
        inputs.get("resolved_project_sha256"), "resolved project SHA", _SHA256
    )
    return {
        **expected,
        "resolved_project_sha256": resolved,
        "target_png_sha256_by_attachment": {
            key: _bytes_sha(value) for key, value in sorted(source_pngs.items())
        },
        "target_rgba_sha256_by_attachment": {
            key: _bytes_sha(value.pixels) for key, value in sorted(images.items())
        },
    }


def _identity(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise VerifiedMeshPipelineError(f"{label} is invalid")
    return value


def _bytes_sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
