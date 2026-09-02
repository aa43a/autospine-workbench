"""Completed-job, persistent-mount, and current-head context tests."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p10_capture_job_contract import (  # noqa: E402
    P10CaptureJobEvent, P10CaptureJobRequest,
)
from autospine_workbench.p10_capture_job_store import (  # noqa: E402
    P10CaptureJobSnapshot,
)
from autospine_workbench.p10_visual_review_v2_context import (  # noqa: E402
    P10VisualReviewV2JobIncomplete, P10VisualReviewV2JobNotFound,
    P10VisualReviewV2SourceChanged,
    resolve_p10_visual_review_v2_context,
)
from autospine_workbench.p10_visual_review_v2_mount_current import (  # noqa: E402
    P10VisualReviewV2MountCurrentError,
)
from autospine_workbench.p10_visual_review_v2_mount_store import (  # noqa: E402
    P10VisualReviewV2MountStoreError,
)


SHA = lambda value: value * 64


class P10VisualReviewV2ContextTests(unittest.TestCase):
    def setUp(self):
        self.p10 = {
            "candidate_sha256": SHA("1"),
            "decision_sha256": SHA("2"), "revision": 3,
        }
        self.framing = {
            "candidate_sha256": SHA("3"),
            "decision_sha256": SHA("4"), "revision": 1,
        }
        self.request = P10CaptureJobRequest.from_payload({
            "package_id": SHA("5"), "client_request_id": "browser-run-1",
            "expected_p10_1": self.p10,
            "expected_framing": self.framing,
            "explicit_runtime_license_confirmation": True,
            "explicit_run_confirmation": True,
        })
        self.addresses = {
            "project": "sample-a", "preview": SHA("6"),
            "execution_bundle": SHA("7"), "artifact": SHA("8"),
        }
        self.snapshot = _completed_snapshot(self.request, self.addresses)
        self.manager = Mock(spec_set=["get"])
        self.manager.get.return_value = self.snapshot
        self.store = SimpleNamespace(
            state_root=Path("state-root"),
            workspace_root=Path("workspace-root"),
        )
        self.preview = SimpleNamespace(
            package_id=SHA("5"), project_id="sample-a",
            clip_id="wave-left-v1", temporary_preview_v2_sha256=SHA("6"),
            artifact_set_sha256=SHA("9"),
            capture_framing_candidate_sha256=SHA("3"),
            capture_framing_decision_sha256=SHA("4"),
            capture_framing_revision=1, case_count=43,
            document={"source": {"current_p10_1_head": self.p10}},
        )
        self.record = SimpleNamespace(result=self.preview)
        self.execution = SimpleNamespace(execution=SimpleNamespace(document={
            "source": {"preview_artifact_set_sha256": SHA("9")},
        }))
        self.verified = SimpleNamespace(result=self.preview)

    @contextmanager
    def harness(
        self, *, cache_record=None, cache_error=None,
        compiler_record=None, current_error=None, save_error=None,
    ):
        reader = Mock(spec_set=["load"])
        reader.load.return_value = self.execution
        reader_type = Mock(return_value=reader)
        cache = Mock(spec_set=["load", "save"])
        cache.load.return_value = cache_record
        cache.load.side_effect = cache_error
        cache.save.side_effect = save_error
        cache_type = Mock(return_value=cache)
        locator = object()
        locator_builder = Mock(return_value=locator)
        compiler = Mock(return_value=compiler_record or self.record)
        current = Mock(side_effect=current_error)
        token_builder = Mock(return_value=self.verified)
        module = "autospine_workbench.p10_visual_review_v2_context"
        with patch(f"{module}.VerifiedBodySwayRuntimeExecutionReader",
                   reader_type), \
                patch(f"{module}.P10VisualReviewV2MountStore", cache_type), \
                patch(f"{module}.p10_preview_v2_cache_locator",
                      locator_builder), \
                patch(f"{module}.compile_cached_body_sway_preview_v2_record",
                      compiler), \
                patch(f"{module}.require_current_p10_visual_review_v2_mount",
                      current), \
                patch(
                    f"{module}.VerifiedP10VisualReviewV2Mount."
                    "from_verified_record", token_builder,
                ):
            yield SimpleNamespace(
                reader=reader, reader_type=reader_type,
                cache=cache, cache_type=cache_type,
                locator=locator, locator_builder=locator_builder,
                compiler=compiler, current=current,
                token_builder=token_builder,
            )

    def resolve(self, *, allow_acceleration=True):
        return resolve_p10_visual_review_v2_context(
            self.manager, self.store, self.request.job_id,
            allow_acceleration=allow_acceleration,
        )

    def test_persistent_hit_skips_full_preview_compile_and_returns_token(self):
        with self.harness(cache_record=self.record) as rig:
            context = self.resolve()

        self.manager.get.assert_called_once_with(self.request.job_id)
        rig.reader_type.assert_called_once_with(self.store.state_root)
        rig.reader.load.assert_called_once_with(
            "sample-a", SHA("6"), SHA("7"), SHA("8"),
        )
        rig.cache.load.assert_called_once_with(
            self.request.job_id, rig.locator,
            expected_preview_sha256=SHA("6"),
            expected_artifact_set_sha256=SHA("9"),
        )
        rig.current.assert_called_once_with(self.store, self.record)
        rig.compiler.assert_not_called()
        rig.cache.save.assert_not_called()
        rig.token_builder.assert_called_once_with(self.record, self.execution)
        self.assertIs(context.preview, self.verified)
        self.assertEqual(
            context.job_head_event_sha256,
            self.snapshot["head_event_sha"],
        )
        self.assertEqual(
            context.job_event_count, self.snapshot["event_count"],
        )
        self.assertEqual(tuple(self.addresses.values()), (
            context.address.project_id,
            context.address.temporary_preview_v2_sha256,
            context.address.runtime_execution_bundle_sha256,
            context.address.capture_artifact_set_sha256,
        ))
        self.assertNotIn("path", str(context.public_job()).lower())

    def test_cache_miss_fully_compiles_and_backfills_snapshot(self):
        with self.harness(cache_record=None) as rig:
            context = self.resolve()

        rig.cache.load.assert_called_once()
        rig.compiler.assert_called_once_with(self.store, SHA("5"))
        rig.cache.save.assert_called_once_with(
            self.request.job_id, self.record,
        )
        rig.current.assert_not_called()
        rig.token_builder.assert_called_once_with(self.record, self.execution)
        self.assertIs(context.preview, self.verified)

    def test_corrupt_cache_is_ignored_then_recompiled_and_replaced(self):
        corrupt = P10VisualReviewV2MountStoreError("corrupt snapshot")
        with self.harness(cache_error=corrupt) as rig:
            context = self.resolve()

        rig.compiler.assert_called_once_with(self.store, SHA("5"))
        rig.cache.save.assert_called_once_with(
            self.request.job_id, self.record,
        )
        rig.current.assert_not_called()
        self.assertIs(context.preview, self.verified)

    def test_compiler_snapshot_rejection_falls_back_to_full_compile(self):
        mismatch = P10VisualReviewV2MountStoreError(
            "Snapshot preview compiler differs"
        )
        with self.harness(cache_error=mismatch) as rig:
            context = self.resolve()

        rig.compiler.assert_called_once_with(self.store, SHA("5"))
        rig.cache.save.assert_called_once_with(
            self.request.job_id, self.record,
        )
        rig.current.assert_not_called()
        self.assertIs(context.preview, self.verified)

    def test_acceleration_disabled_forces_compile_without_cache_io(self):
        with self.harness(cache_record=self.record) as rig:
            context = self.resolve(allow_acceleration=False)

        rig.cache.load.assert_not_called()
        rig.current.assert_not_called()
        rig.compiler.assert_called_once_with(self.store, SHA("5"))
        rig.cache.save.assert_not_called()
        self.assertIs(context.preview, self.verified)

    def test_cache_write_failure_does_not_turn_acceleration_into_authority(self):
        unavailable = P10VisualReviewV2MountStoreError("read-only cache")
        with self.harness(cache_record=None, save_error=unavailable) as rig:
            context = self.resolve()

        rig.compiler.assert_called_once_with(self.store, SHA("5"))
        rig.cache.save.assert_called_once()
        rig.token_builder.assert_called_once_with(self.record, self.execution)
        self.assertIs(context.preview, self.verified)

    def test_cached_mount_currentness_drift_fails_without_compile_fallback(self):
        drift = P10VisualReviewV2MountCurrentError("current head changed")
        with self.harness(
            cache_record=self.record, current_error=drift,
        ) as rig, self.assertRaises(P10VisualReviewV2SourceChanged):
            self.resolve()

        rig.current.assert_called_once_with(self.store, self.record)
        rig.compiler.assert_not_called()
        rig.cache.save.assert_not_called()
        rig.token_builder.assert_not_called()

    def test_job_expected_heads_and_preview_address_drift_fail_closed(self):
        variants = []
        changed = SimpleNamespace(**vars(self.preview))
        changed.document = {"source": {"current_p10_1_head": {
            **self.p10, "revision": 4,
        }}}
        variants.append(changed)
        changed = SimpleNamespace(**vars(self.preview))
        changed.capture_framing_revision = 2
        variants.append(changed)
        changed = SimpleNamespace(**vars(self.preview))
        changed.temporary_preview_v2_sha256 = SHA("a")
        variants.append(changed)

        for changed in variants:
            with self.subTest(changed=changed), self.harness(
                cache_record=SimpleNamespace(result=changed),
            ) as rig, self.assertRaises(P10VisualReviewV2SourceChanged):
                self.resolve()
            rig.compiler.assert_not_called()
            rig.token_builder.assert_not_called()

    def test_incomplete_job_is_zero_execution_and_mount_replay(self):
        self.snapshot.update({
            "status": "capturing", "terminal": False,
            "addresses": None,
        })
        with self.harness(cache_record=self.record) as rig, \
                self.assertRaises(P10VisualReviewV2JobIncomplete):
            self.resolve()

        rig.reader_type.assert_not_called()
        rig.locator_builder.assert_not_called()
        rig.cache_type.assert_not_called()
        rig.cache.load.assert_not_called()
        rig.compiler.assert_not_called()
        rig.current.assert_not_called()
        rig.token_builder.assert_not_called()

    def test_tampered_job_or_request_identity_is_not_found_before_replay(self):
        for field, value in (
            ("job_id", SHA("0")),
            ("request", {**self.request.public_document(),
                         "package_id": SHA("0")}),
        ):
            with self.subTest(field=field):
                self.manager.reset_mock()
                self.manager.get.return_value = {
                    **self.snapshot, field: value,
                }
                with self.harness(cache_record=self.record) as rig, \
                        self.assertRaises(P10VisualReviewV2JobNotFound):
                    self.resolve()
                rig.reader_type.assert_not_called()
                rig.cache_type.assert_not_called()
                rig.compiler.assert_not_called()

    def test_tampered_completed_event_chain_is_rejected_before_replay(self):
        changed = dict(self.snapshot)
        changed["head_event_sha"] = SHA("e")
        self.manager.get.return_value = changed
        with self.harness(cache_record=self.record) as rig, \
                self.assertRaises(P10VisualReviewV2JobNotFound):
            self.resolve()
        rig.reader_type.assert_not_called()
        rig.cache_type.assert_not_called()
        rig.compiler.assert_not_called()


def _completed_snapshot(request, addresses):
    rows = (
        ("queued", {}), ("exact_replay", {}),
        ("preview_compiled", {}), ("runtime_verified", {}),
        ("capturing", {"current": 1, "total": 1}),
        ("sealing", {}), ("completed", {"addresses": addresses}),
    )
    events = []
    previous = None
    for sequence, (status, payload) in enumerate(rows, 1):
        event = P10CaptureJobEvent.build(
            request.job_id, sequence, status,
            previous.event_sha if previous else None, **payload,
        )
        events.append(event)
        previous = event
    return P10CaptureJobSnapshot(request, tuple(events)).public_document()


if __name__ == "__main__":
    unittest.main()
