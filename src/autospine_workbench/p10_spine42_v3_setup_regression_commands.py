"""Read-only command boundary for the P10.7c setup golden comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from .p6_spine42_approval import (
    P6Spine42ApprovalError,
    require_p6_spine42_approval,
)
from .safe_input_files import SafeInputFileError, read_real_file, strict_json_object
from .spine42_runtime_contract import (
    Spine42RuntimeContractError,
    require_runtime_golden,
)
from .spine42_runtime_regression import MAX_CAPTURE_BYTES
from .spine42_bundle_integrity import VerifiedSpine42BundleReader
from .spine42_v3_bundle_reader import VerifiedSpine42V3BundleReader
from .spine42_v3_runtime_reader import VerifiedSpine42V3RuntimeReader
from .spine42_v3_setup_regression_binding import (
    Spine42V3SetupRegressionBindingError,
    build_bound_spine42_v3_setup_regression_report,
)
from .spine42_v3_setup_regression_manifest import (
    MAX_REQUEST_BYTES,
    Spine42V3SetupRegressionManifestError,
    parse_spine42_v3_setup_regression_request,
    setup_regression_request_sha256,
)
from .spine42_v3_setup_regression_report import Spine42V3SetupRegressionReportError


MAX_APPROVAL_BYTES = 16 * 1024 * 1024


class P10Spine42V3SetupRegressionCommandError(RuntimeError):
    """Fixed path-free failure boundary for the P10.7c command."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3SetupRegressionCommandResult:
    request_sha256: str
    report_sha256: str
    status: str
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


def compare_body_sway_spine42_v3_setup_command(
    state_root: Path,
    manifest_path: Path,
    p6_export_contract_path: Path,
    runtime_golden_contract_path: Path,
) -> P10Spine42V3SetupRegressionCommandResult:
    """Read exact contracts and state once, compare, and write nothing."""

    try:
        request_raw = read_real_file(
            manifest_path, MAX_REQUEST_BYTES, "setup regression request"
        )
        p6_raw = read_real_file(
            p6_export_contract_path, MAX_APPROVAL_BYTES,
            "approved P6 export contract",
        )
        runtime_raw = read_real_file(
            runtime_golden_contract_path, MAX_APPROVAL_BYTES,
            "approved runtime golden contract",
        )
        request = parse_spine42_v3_setup_regression_request(request_raw)
        if _sha(p6_raw) != request["approved_p6_export_contract_sha256"] \
                or _sha(runtime_raw) != \
                    request["approved_runtime_golden_sha256"]:
            raise P10Spine42V3SetupRegressionCommandError(
                "Approved contract bytes differ from the request"
            )
        p6 = require_p6_spine42_approval(strict_json_object(
            p6_raw, "approved P6 export contract"
        ))
        runtime_golden = require_runtime_golden(strict_json_object(
            runtime_raw, "approved runtime golden contract"
        ))
        golden_bytes = _approved_png_snapshots(
            request, runtime_golden, Path(runtime_golden_contract_path).parent
        )
        state = Path(state_root)
        p6_reader = VerifiedSpine42BundleReader(state)
        spine_reader = VerifiedSpine42V3BundleReader(state)
        runtime_reader = VerifiedSpine42V3RuntimeReader(state)
        exact_sources = []
        for sample in request["samples"]:
            spine_address = sample["spine42_v3_address"]
            capture_address = sample["runtime_capture_address"]
            p6_address = sample["p6_setup_address"]
            p6_bundle = p6_reader.load(
                sample["project_id"], p6_address["skeleton_json_sha256"],
                p6_address["bundle_sha256"],
            )
            spine = spine_reader.load(
                sample["project_id"], spine_address["skeleton_json_sha256"],
                spine_address["bundle_sha256"],
            )
            capture = runtime_reader.load(
                sample["project_id"],
                capture_address["spine42_v3_bundle_sha256"],
                capture_address["capture_bundle_sha256"],
            )
            exact_sources.append((p6_bundle, spine, capture))
        report = build_bound_spine42_v3_setup_regression_report(
            request, p6, runtime_golden, golden_bytes, exact_sources,
        )
        canonical = json.dumps(
            report, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        return P10Spine42V3SetupRegressionCommandResult(
            setup_regression_request_sha256(request),
            report["setup_regression_report_sha256"],
            report["status"], canonical,
        )
    except P10Spine42V3SetupRegressionCommandError:
        raise
    except _FAILURES as exc:
        raise P10Spine42V3SetupRegressionCommandError(
            "Body-sway Spine 4.2 v3 setup regression failed"
        ) from exc


def _approved_png_snapshots(request, golden, root: Path) -> dict[str, bytes]:
    cases = {row["id"]: row for row in golden["cases"]}
    result = {}
    for sample in request["samples"]:
        case_id = sample["approved_runtime_case_id"]
        case = cases.get(case_id)
        if case is None:
            raise P10Spine42V3SetupRegressionCommandError(
                "Approved runtime case is absent"
            )
        if case_id not in result:
            result[case_id] = read_real_file(
                root / case["golden"]["path"],
                MAX_CAPTURE_BYTES,
                "approved setup PNG",
            )
    return result


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


_FAILURES = (
    AttributeError, KeyError, OSError, OverflowError, P6Spine42ApprovalError,
    RecursionError, RuntimeError, SafeInputFileError,
    Spine42RuntimeContractError, Spine42V3SetupRegressionBindingError,
    Spine42V3SetupRegressionManifestError,
    Spine42V3SetupRegressionReportError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "MAX_APPROVAL_BYTES", "P10Spine42V3SetupRegressionCommandError",
    "P10Spine42V3SetupRegressionCommandResult",
    "compare_body_sway_spine42_v3_setup_command",
]
