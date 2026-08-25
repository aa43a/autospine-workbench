"""Semantic contract checks for P2 compile-run and setup-probe artifacts."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


_STATUSES = frozenset({"passed", "manual_required", "rejected"})
_REQUIRED_CHECKS = frozenset(
    {
        "source.identity",
        "inputs.reviewed",
        "bones.parent-links",
        "fk.setup-reconstruction",
        "attachments.region-bindings",
        "attachments.pivot-roundtrip",
        "slots.draw-order",
        "setup.pixel-reconstruction",
    }
)


class RigArtifactValidationError(ValueError):
    """Raised when a P2 artifact has an unsupported or incomplete contract."""


def require_compile_run_document(run: Mapping[str, Any]) -> None:
    _exact_keys(
        run,
        {"format", "format_version", "project_id", "inputs", "compiler"},
        "compile run",
    )
    if run.get("format") != "autospine-rig-compile-run" or run.get("format_version") != 1:
        raise RigArtifactValidationError("Compile run format is unsupported")
    inputs = _mapping(run.get("inputs"), "compile run inputs")
    _keys_with_optional(
        inputs,
        {"layer_manifest_sha256", "resolved_project_sha256"},
        {"override_patch_sha256"},
        "compile run inputs",
    )
    compiler = _mapping(run.get("compiler"), "compile run compiler")
    _exact_keys(compiler, {"id", "version", "config"}, "compile run compiler")
    if compiler.get("id") != "region-rig-compiler" or not _version(compiler.get("version")):
        raise RigArtifactValidationError("Compile run compiler identity is invalid")
    config = _mapping(compiler.get("config"), "compile run config")
    _exact_keys(
        config,
        {"attachment_profile", "allow_manual_required"},
        "compile run config",
    )
    if config.get("attachment_profile") != "region-only" or not isinstance(
        config.get("allow_manual_required"), bool
    ):
        raise RigArtifactValidationError("Compile run profile is invalid")


def require_setup_probe_document(report: Mapping[str, Any]) -> None:
    _exact_keys(
        report,
        {"format", "format_version", "project_id", "source", "runner", "status", "checks"},
        "setup probe report",
    )
    if report.get("format") != "autospine-rig-setup-probes" or report.get("format_version") != 1:
        raise RigArtifactValidationError("Setup probe format is unsupported")
    source = _mapping(report.get("source"), "setup probe source")
    _exact_keys(
        source,
        {"rig_sha256", "layer_manifest_sha256", "resolved_project_sha256"},
        "setup probe source",
    )
    runner = _mapping(report.get("runner"), "setup probe runner")
    _exact_keys(runner, {"id", "version"}, "setup probe runner")
    if runner.get("id") != "rig-setup-probes" or not _version(runner.get("version")):
        raise RigArtifactValidationError("Setup probe runner identity is invalid")
    checks = report.get("checks")
    if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes)) or not checks:
        raise RigArtifactValidationError("Setup probe checks must be a non-empty array")
    statuses: list[str] = []
    ids: set[str] = set()
    for index, raw in enumerate(checks):
        check = _mapping(raw, f"setup probe check {index}")
        _keys_with_optional(check, {"id", "status"}, {"message", "metrics"}, f"check {index}")
        check_id, status = check.get("id"), check.get("status")
        if not isinstance(check_id, str) or not check_id or check_id in ids:
            raise RigArtifactValidationError("Setup probe check ids must be non-empty and unique")
        if status not in _STATUSES:
            raise RigArtifactValidationError(f"Setup probe check {check_id} has invalid status")
        if "message" in check and not isinstance(check["message"], str):
            raise RigArtifactValidationError(f"Setup probe check {check_id} message is invalid")
        if "metrics" in check and not isinstance(check["metrics"], Mapping):
            raise RigArtifactValidationError(f"Setup probe check {check_id} metrics are invalid")
        ids.add(check_id)
        statuses.append(status)
    missing = sorted(_REQUIRED_CHECKS - ids)
    if missing:
        raise RigArtifactValidationError(f"Setup probe report is missing checks: {', '.join(missing)}")
    aggregate = _aggregate_status(statuses)
    if report.get("status") != aggregate or aggregate == "rejected":
        raise RigArtifactValidationError("Setup probe aggregate status is invalid or rejected")
    pixel = next(check for check in checks if check["id"] == "setup.pixel-reconstruction")
    if pixel.get("status") != "passed" or (pixel.get("metrics") or {}).get("exact") is not True:
        raise RigArtifactValidationError("Setup pixel reconstruction did not pass exactly")


def require_region_rig_profile(rig: Mapping[str, Any]) -> None:
    if rig.get("capabilities") != ["region_attachment", "setup_draw_order"]:
        raise RigArtifactValidationError("RigIR capabilities do not match the region-only profile")
    if rig.get("animations") != []:
        raise RigArtifactValidationError("Region-only RigIR cannot contain animations")
    attachments = rig.get("attachments")
    if not isinstance(attachments, list) or any(
        not isinstance(item, Mapping)
        or item.get("type") != "region"
        or not isinstance(item.get("source_layer_ids"), list)
        or len(item["source_layer_ids"]) != 1
        for item in attachments
    ):
        raise RigArtifactValidationError("RigIR attachments do not match the region-only profile")
    status = (rig.get("qa") or {}).get("status")
    if status not in {"passed", "manual_required"}:
        raise RigArtifactValidationError("RigIR QA status is invalid or rejected")


def _aggregate_status(statuses: Sequence[str]) -> str:
    if "rejected" in statuses:
        return "rejected"
    if "manual_required" in statuses:
        return "manual_required"
    return "passed"


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RigArtifactValidationError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], required: set[str], label: str) -> None:
    if set(value) != required:
        raise RigArtifactValidationError(f"{label} fields are incomplete or unsupported")


def _keys_with_optional(
    value: Mapping[str, Any], required: set[str], optional: set[str], label: str
) -> None:
    keys = set(value)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise RigArtifactValidationError(f"{label} fields are incomplete or unsupported")


def _version(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 64
