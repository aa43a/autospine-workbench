"""Pure runtime run snapshot validation; never issues execution authority."""

from .spine42_v3_runtime_capture_report import require_capture_snapshot_consistency
from .spine42_v3_runtime_session_v2 import require_exact_spine42_v3_runtime_sessions_v2
from .spine42_v3_runtime_session_core import canonical_json


def run_state(bundle, source, runtime, browser, sessions, snapshot, error_type):
    require_exact_spine42_v3_runtime_sessions_v2(
        bundle, runtime, source, sessions,
    )
    captures, reports = snapshot.capture_bytes, snapshot.reports
    artifact_ids = sessions.artifact_ids
    if tuple(captures) != artifact_ids or len(reports) != len(artifact_ids):
        raise error_type("Runtime snapshot order is invalid")
    require_capture_snapshot_consistency(
        artifact_ids, sessions.session_bytes, captures,
        dict(zip(artifact_ids, reports, strict=True)),
        error_type=error_type,
    )
    return (
        bundle.project_id, bundle.clip_id, bundle.skeleton_json_sha256,
        bundle.bundle_sha256, source.admission_sha256,
        source.capture_plan_sha256, sessions.sha256,
        runtime.package_json_sha256, runtime.license_sha256,
        browser.family, browser.reported_version,
        browser.version_output_sha256, browser.executable_sha256,
        browser.size_bytes, len(captures), True,
        canonical_json(sessions.plan), canonical_json(sessions.source_admission),
        canonical_json(list(reports)), tuple(captures.items()),
    )
