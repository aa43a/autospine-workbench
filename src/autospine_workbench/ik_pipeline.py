"""Pure verified-P3 to P4 IK profile and probe orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from .ik_probe_report import build_ik_probe_report, require_ik_probe_report
from .ik_target_profile import (
    SOURCE_IDENTITY_FIELDS,
    compile_ik_target_profile,
)
from .ik_target_profile_validation import require_ik_target_profile
from .mesh_bundle_reader import VerifiedMeshBundleReader
from .resolved_project import canonical_sha256


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class VerifiedIkPipelineError(RuntimeError):
    """Raised when an exact P3 address cannot produce passed P4 evidence."""


@dataclass(frozen=True, slots=True)
class VerifiedIkPipelineResult:
    """Frozen canonical P4 documents and their complete identity chain."""

    project_id: str
    summary: str
    _profile_json: str = field(repr=False)
    _probes_json: str = field(repr=False)
    _input_sha_json: str = field(repr=False)
    _output_sha_json: str = field(repr=False)

    @property
    def profile(self) -> dict[str, Any]:
        return json.loads(self._profile_json)

    @property
    def probes(self) -> dict[str, Any]:
        return json.loads(self._probes_json)

    @property
    def input_sha256s(self) -> dict[str, str]:
        return json.loads(self._input_sha_json)

    @property
    def output_sha256s(self) -> dict[str, str]:
        return json.loads(self._output_sha_json)


@dataclass(frozen=True, slots=True)
class VerifiedIkPipeline:
    """Build P4 documents only after a strict exact P3 bundle read."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def build(
        self,
        project_id: str,
        p3_rig_sha256: str,
        p3_bundle_sha256: str,
    ) -> VerifiedIkPipelineResult:
        """Compile the immutable profile and recomputable numerical probes."""

        try:
            project = _identity(project_id, "project id", _SAFE_ID)
            rig_sha = _identity(p3_rig_sha256, "P3 RigIR SHA", _SHA256)
            bundle_sha = _identity(
                p3_bundle_sha256, "P3 bundle SHA", _SHA256
            )
            base = VerifiedMeshBundleReader(self.state_root).load(
                project, rig_sha, bundle_sha
            )
            if (
                base.project_id != project
                or base.rig_sha256 != rig_sha
                or base.bundle_sha256 != bundle_sha
            ):
                raise VerifiedIkPipelineError(
                    "Verified P3 result differs from the requested exact address"
                )
            profile = compile_ik_target_profile(base).document
            require_ik_target_profile(profile, verified_bundle=base)
            probes = build_ik_probe_report(profile).document
            require_ik_probe_report(probes, profile=profile)
            if probes.get("status") != "passed":
                raise VerifiedIkPipelineError("P4 numerical probes did not pass")
            handles = profile.get("handles")
            if not isinstance(handles, list) or len(handles) != 4:
                raise VerifiedIkPipelineError("P4 target inventory is incomplete")
            input_shas = {
                field: getattr(base, field) for field in SOURCE_IDENTITY_FIELDS
            }
            if profile.get("source") != input_shas:
                raise VerifiedIkPipelineError("P4 input identity chain drifted")
            output_shas = {
                "profile_sha256": canonical_sha256(profile),
                "probes_sha256": canonical_sha256(probes),
            }
            return VerifiedIkPipelineResult(
                project_id=project,
                summary=f"handles={len(handles)}",
                _profile_json=_encode(profile),
                _probes_json=_encode(probes),
                _input_sha_json=_encode(input_shas),
                _output_sha_json=_encode(output_shas),
            )
        except VerifiedIkPipelineError:
            raise
        except (
            AttributeError,
            KeyError,
            OverflowError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VerifiedIkPipelineError(
                f"Verified IK pipeline failed: {exc}"
            ) from exc


def _identity(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise VerifiedIkPipelineError(f"{label} is invalid")
    return value


def _encode(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
