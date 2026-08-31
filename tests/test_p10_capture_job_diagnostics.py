"""Safe, replay-derived diagnostics for immutable P10 capture failures."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_capture_job_contract import (  # noqa: E402
    P10CaptureJobEvent,
)
from autospine_workbench.p10_capture_job_diagnostics import (  # noqa: E402
    capture_failure_diagnostic,
)


JOB = "a" * 64


class P10CaptureJobDiagnosticTests(unittest.TestCase):
    def test_case_failure_reports_only_replayable_stage_and_counts(self):
        events = chain(
            ("queued", {}),
            ("exact_replay", {}),
            ("preview_compiled", {}),
            ("runtime_verified", {}),
            ("capturing", {"current": 0, "total": 43}),
            ("capturing", {"current": 13, "total": 43}),
            ("failed_retryable", {"failure_code": "runtime_capture_failed"}),
        )
        value = capture_failure_diagnostic(events)
        self.assertEqual({
            "format": "autospine-p10-capture-failure-diagnostic",
            "format_version": 1,
            "stage": "case_capture",
            "category": "runtime_execution",
            "completed_case_count": 13,
            "total_case_count": 43,
            "next_incomplete_case_ordinal": 14,
        }, value)
        self.assertNotIn("path", repr(value).lower())

    def test_failure_after_all_cases_is_capture_compilation(self):
        events = chain(
            ("queued", {}),
            ("exact_replay", {}),
            ("preview_compiled", {}),
            ("runtime_verified", {}),
            ("capturing", {"current": 2, "total": 2}),
            ("failed_retryable", {"failure_code": "runtime_capture_failed"}),
        )
        value = capture_failure_diagnostic(events)
        self.assertEqual("capture_compilation", value["stage"])
        self.assertIsNone(value["next_incomplete_case_ordinal"])

    def test_nonfailure_has_no_diagnostic_and_unknown_code_is_bounded(self):
        active = chain(("queued", {}), ("exact_replay", {}))
        self.assertIsNone(capture_failure_diagnostic(active))
        failed = chain(
            ("queued", {}),
            ("failed_retryable", {"failure_code": "future_safe_code"}),
        )
        value = capture_failure_diagnostic(failed)
        self.assertEqual("input_replay", value["stage"])
        self.assertEqual("unclassified", value["category"])
        self.assertIsNone(value["completed_case_count"])


def chain(*specifications):
    events = []
    for sequence, (status, payload) in enumerate(specifications, start=1):
        kwargs = dict(payload)
        if status == "capturing":
            progress = kwargs.pop("current"), kwargs.pop("total")
            kwargs.update(current=progress[0], total=progress[1])
        event = P10CaptureJobEvent.build(
            JOB, sequence, status,
            events[-1].event_sha if events else None,
            **kwargs,
        )
        events.append(event)
    return tuple(events)


if __name__ == "__main__":
    unittest.main()
