"""Contract tests for the P10.7b v2 authorized runtime job journal."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
)
from autospine_workbench.p10_spine42_v3_runtime_job_contract_v2 import (
    P10Spine42V3RuntimeJobContractV2Error,
    P10Spine42V3RuntimeJobEventV2,
    P10Spine42V3RuntimeJobRequestV2,
    require_runtime_job_source_binding_v2,
    require_runtime_job_transition_v2,
)
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.spine42_runtime_inputs import Spine42RuntimePackage


def _sha(character: str) -> str:
    return character * 64


def _runtime() -> Spine42RuntimePackage:
    return Spine42RuntimePackage(
        Path("X:/private/runtime"), Path("X:/private/runtime/player.js"),
        Path("X:/private/runtime/player.css"),
        Path("X:/private/runtime/LICENSE"), b"js", b"css", _sha("a"),
        _sha("b"), _sha("c"), _sha("d"),
    )


def _browser() -> BrowserExecutableSnapshot:
    return BrowserExecutableSnapshot(
        "X:/private/chrome.exe", "chrome", "Chrome 140.0.0.0",
        _sha("e"), _sha("f"), 123456,
    )


def _payload(**changes):
    value = {
        "candidate_id": _sha("1"), "entry_sha256": _sha("2"),
        "authorization_id": "auth-00000001", "retry_of_job_id": None,
        "explicit_runtime_license_confirmation": True,
        "explicit_run_confirmation": True,
    }
    value.update(changes)
    return value


def _request(**changes):
    payload = _payload(**changes)
    return P10Spine42V3RuntimeJobRequestV2.expand(
        payload, project_id="sample", clip_id="idle",
        skeleton_json_sha256=_sha("3"),
        spine42_v3_bundle_sha256=_sha("4"),
        runtime=_runtime(), browser=_browser(),
    )


def _address():
    return {
        "project_id": "sample", "skeleton_json_sha256": _sha("3"),
        "spine42_v3_bundle_sha256": _sha("4"),
        "capture_bundle_sha256": _sha("5"),
    }


class P10Spine42V3RuntimeJobContractV2Tests(unittest.TestCase):
    def test_browser_payload_expands_to_path_free_exact_request(self):
        request = _request()
        document = request.document
        self.assertEqual(2, document["format_version"])
        self.assertEqual("sample", document["source"]["project_id"])
        self.assertEqual(_sha("c"),
                         document["runtime"]["package_json_sha256"])
        self.assertEqual(_sha("f"),
                         document["browser"]["executable_sha256"])
        self.assertNotIn("path", repr(document).lower())
        self.assertNotIn("private", repr(document).lower())
        rebuilt = P10Spine42V3RuntimeJobRequestV2.from_document(
            dict(reversed(tuple(document.items())))
        )
        self.assertEqual(request.job_id, rebuilt.job_id)
        self.assertNotEqual(
            request.job_id,
            canonical_sha256({"domain": "autospine-p10-capture-job-id/v1",
                              "request": document}),
        )

    def test_both_confirmations_are_strict_true_and_fields_are_exact(self):
        for field in (
            "explicit_runtime_license_confirmation",
            "explicit_run_confirmation",
        ):
            for bad in (False, 1, "true", None):
                with self.subTest(field=field, bad=bad), self.assertRaises(
                    P10Spine42V3RuntimeJobContractV2Error
                ):
                    _request(**{field: bad})
        for changes in (
            {"extra": True}, {"candidate_id": _sha("A")},
            {"authorization_id": "Auth-00000001"},
            {"retry_of_job_id": "bad"},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                P10Spine42V3RuntimeJobContractV2Error
            ):
                _request(**changes)

    def test_environment_types_and_exact_document_are_required(self):
        with self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
            P10Spine42V3RuntimeJobRequestV2.expand(
                _payload(), project_id="sample", clip_id="idle",
                skeleton_json_sha256=_sha("3"),
                spine42_v3_bundle_sha256=_sha("4"),
                runtime=replace(_runtime(), package_json_sha256=""),
                browser=_browser(),
            )
        changed = _request().document
        changed["source"]["private_path"] = "X:/escape"
        with self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
            P10Spine42V3RuntimeJobRequestV2.from_document(changed)

    def test_format_versions_require_an_integer_not_numeric_equality(self):
        request = _request().document
        request["format_version"] = 2.0
        with self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
            P10Spine42V3RuntimeJobRequestV2.from_document(request)
        job = _request()
        event = P10Spine42V3RuntimeJobEventV2.build(
            job.job_id, 1, None, "queued", "queued").document
        event["format_version"] = 2.0
        with self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
            P10Spine42V3RuntimeJobEventV2.from_document(event)

    def test_event_chain_requires_complete_capture_before_compilation(self):
        request = _request()
        queued = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 1, None, "queued", "queued",
        )
        exact = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 2, queued.event_sha256,
            "running", "exact_source_readback",
        )
        verified = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 3, exact.event_sha256,
            "running", "runtime_reverified",
        )
        capture = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 4, verified.event_sha256,
            "running", "capturing", current=0, total=3,
        )
        for left, right in (
            (None, queued), (queued, exact), (exact, verified),
            (verified, capture),
        ):
            require_runtime_job_transition_v2(left, right)
        compile_event = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 5, capture.event_sha256,
            "running", "evidence_compiling",
        )
        with self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
            require_runtime_job_transition_v2(capture, compile_event)

        skipped = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 5, capture.event_sha256,
            "running", "capturing", current=2, total=3,
        )
        with self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
            require_runtime_job_transition_v2(capture, skipped)
        changed_failure_progress = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 5, capture.event_sha256,
            "failed_retryable", "capturing", current=17, total=99,
            failure_code="capture_failed", resume_mode="new_authorization",
        )
        with self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
            require_runtime_job_transition_v2(capture, changed_failure_progress)

    def test_publication_checkpoint_and_completed_result_are_exact(self):
        request = _request()
        with self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
            P10Spine42V3RuntimeJobEventV2.build(
                request.job_id, 1, None, "running", "publishing",
            )
        completed = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 8, _sha("6"), "completed", "completed",
            current=1, total=1, result=_address(),
        )
        self.assertEqual(set(_address()), set(completed.document["result"]))
        self.assertNotIn("path", repr(completed.public_document()).lower())

    def test_active_cannot_skip_or_repeat_non_capture_stage(self):
        request = _request()
        queued = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 1, None, "queued", "queued",
        )
        completed = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 2, queued.event_sha256,
            "completed", "completed", current=1, total=1,
            result=_address(),
        )
        wrong_failure = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 2, queued.event_sha256,
            "failed_retryable", "capturing", failure_code="failed",
            resume_mode="new_authorization",
        )
        exact = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 2, queued.event_sha256,
            "running", "exact_source_readback",
        )
        repeated = P10Spine42V3RuntimeJobEventV2.build(
            request.job_id, 3, exact.event_sha256,
            "running", "exact_source_readback",
        )
        for left, right in (
            (queued, completed), (queued, wrong_failure), (exact, repeated),
        ):
            with self.subTest(status=right.document["status"]), \
                    self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
                require_runtime_job_transition_v2(left, right)

    def test_all_terminal_events_have_no_outgoing_transition(self):
        request = _request()
        for status, mode in (
            ("completed", None), ("failed_retryable", "new_authorization"),
            ("interrupted_retryable", "new_authorization"),
            ("failed_terminal", None),
        ):
            result = _address() if status == "completed" else None
            checkpoint = _address() if status != "completed" and (
                mode is None or status == "interrupted_retryable"
            ) else None
            failure = None if status == "completed" else "fixture_failure"
            stage = "completed" if status == "completed" else (
                "parent_exact_readback" if checkpoint is not None
                else "capturing"
            )
            terminal = P10Spine42V3RuntimeJobEventV2.build(
                request.job_id, 2, _sha("7"), status, stage,
                current=1 if status == "completed" else 0, total=1,
                failure_code=failure, resume_mode=mode,
                capture_address=checkpoint, result=result,
            )
            next_event = P10Spine42V3RuntimeJobEventV2.build(
                request.job_id, 3, terminal.event_sha256,
                "running", "exact_source_readback",
            )
            with self.subTest(status=status), self.assertRaises(
                P10Spine42V3RuntimeJobContractV2Error
            ):
                require_runtime_job_transition_v2(terminal, next_event)

    def test_capture_addresses_are_bound_to_request_source(self):
        request = _request()
        variants = {
            "project_id": "other", "skeleton_json_sha256": _sha("8"),
            "spine42_v3_bundle_sha256": _sha("9"),
        }
        for field, value in variants.items():
            address = _address()
            address[field] = value
            events = (
                P10Spine42V3RuntimeJobEventV2.build(
                    request.job_id, 2, _sha("6"), "running", "publishing",
                    capture_address=address),
                P10Spine42V3RuntimeJobEventV2.build(
                    request.job_id, 2, _sha("6"), "failed_retryable",
                    "publishing", failure_code="readback_not_found",
                    resume_mode="new_authorization", capture_address=address),
                P10Spine42V3RuntimeJobEventV2.build(
                    request.job_id, 2, _sha("6"), "completed", "completed",
                    current=1, total=1, result=address),
            )
            for event in events:
                with self.subTest(field=field, status=event.document["status"]), \
                        self.assertRaises(P10Spine42V3RuntimeJobContractV2Error):
                    require_runtime_job_source_binding_v2(request, event)


if __name__ == "__main__":
    unittest.main()
