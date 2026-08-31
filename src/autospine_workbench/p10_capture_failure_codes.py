"""Path-free failure codes for P10 official Runtime job events."""

from __future__ import annotations


_HEADLESS_PREFIX_CODES = (
    ("Official runtime reported a terminal capture error",
     "runtime_page_reported_error"),
    ("Headless browser exited with non-zero status",
     "runtime_browser_nonzero_exit"),
    ("Headless browser exited without posting the exact capture",
     "runtime_browser_exited_without_capture"),
    ("Headless browser capture timed out", "runtime_browser_timeout"),
    ("Headless browser output exceeded", "runtime_browser_output_limit"),
    ("Headless browser output could not be read",
     "runtime_browser_output_failed"),
    ("Headless browser process-tree isolation failed",
     "runtime_browser_process_control_failed"),
    ("Headless browser process-tree cleanup failed",
     "runtime_browser_process_control_failed"),
    ("Headless browser could not be started or monitored",
     "runtime_browser_launch_failed"),
)

_TYPE_CODES = {
    "BodySwayBrowserProfileLeaseError":
        "runtime_browser_profile_cleanup_failed",
    "BodySwayCaptureServerLeaseError": "runtime_capture_server_failed",
    "BodySwayHeadlessBrowserError": "runtime_browser_case_failed",
    "BrowserExecutableSnapshotError": "runtime_browser_identity_changed",
    "LockedBrowserExecutableLeaseError": "runtime_browser_identity_changed",
    "BodySwayRuntimeCaptureV2CompilerError":
        "runtime_case_evidence_failed",
    "BodySwayRuntimeExecutionError": "runtime_evidence_validation_failed",
    "BodySwayRuntimeExecutionStoreError":
        "runtime_evidence_publication_failed",
    "VerifiedBodySwayRuntimeExecutionReaderError":
        "runtime_evidence_validation_failed",
}


def classify_p10_capture_failure(error: BaseException) -> str:
    """Return one bounded code without retaining exception text or paths."""

    for current in _exception_chain(error):
        name = type(current).__name__
        if name == "BodySwayHeadlessBrowserError":
            message = str(current)
            for prefix, code in _HEADLESS_PREFIX_CODES:
                if message.startswith(prefix):
                    return code
        code = _TYPE_CODES.get(name)
        if code is not None:
            return code
    return "runtime_capture_failed"


def _exception_chain(error):
    seen: set[int] = set()
    current = error
    for _depth in range(12):
        if not isinstance(current, BaseException) or id(current) in seen:
            return
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


__all__ = ["classify_p10_capture_failure"]
