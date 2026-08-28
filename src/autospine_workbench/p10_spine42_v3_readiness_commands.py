"""Read-only command boundary for P10.7 real-sample readiness audits."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .safe_input_files import SafeInputFileError, read_real_file
from .spine42_v3_readiness import audit_spine42_v3_readiness
from .spine42_v3_readiness_binding import (
    Spine42V3ReadinessBindingError,
    require_spine42_v3_readiness_report_binding,
)
from .spine42_v3_readiness_manifest import (
    MAX_REQUEST_BYTES,
    Spine42V3ReadinessManifestError,
    parse_spine42_v3_readiness_request,
    spine42_v3_readiness_request_sha256,
)


class P10Spine42V3ReadinessCommandError(RuntimeError):
    """Fixed path-free failure boundary for one readiness audit."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3ReadinessCommandResult:
    """Copy-isolated readiness report and exact request identity."""

    request_sha256: str
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


ReadinessEvaluator = Callable[
    [Mapping[str, Any], Path], Mapping[str, Any]
]


def audit_body_sway_spine42_v3_readiness_command(
    state_root: Path,
    manifest_path: Path,
    *,
    evaluator: ReadinessEvaluator | None = None,
) -> P10Spine42V3ReadinessCommandResult:
    """Read one strict request and audit only its explicit addresses."""

    try:
        raw = read_real_file(
            manifest_path,
            MAX_REQUEST_BYTES,
            "Spine 4.2 v3 readiness request",
        )
        request = parse_spine42_v3_readiness_request(raw)
        request_sha = spine42_v3_readiness_request_sha256(request)
        implementation = evaluator or audit_spine42_v3_readiness
        report = implementation(request, Path(state_root))
        if type(report) is not dict:
            raise TypeError("Readiness evaluator must return a JSON object")
        require_spine42_v3_readiness_report_binding(report, request)
        canonical = json.dumps(
            report,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return P10Spine42V3ReadinessCommandResult(
            request_sha256=request_sha,
            _canonical_json=canonical,
        )
    except P10Spine42V3ReadinessCommandError:
        raise
    except _COMMAND_FAILURES as exc:
        raise P10Spine42V3ReadinessCommandError(
            "Body-sway Spine 4.2 v3 readiness audit failed"
        ) from exc


_COMMAND_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    OverflowError,
    RecursionError,
    RuntimeError,
    SafeInputFileError,
    Spine42V3ReadinessManifestError,
    Spine42V3ReadinessBindingError,
    TypeError,
    UnicodeError,
    ValueError,
)


__all__ = [
    "P10Spine42V3ReadinessCommandError",
    "P10Spine42V3ReadinessCommandResult",
    "audit_body_sway_spine42_v3_readiness_command",
]
