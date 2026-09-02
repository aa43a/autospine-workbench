"""Concurrency, crash-window, and tamper tests for P10.7b v2 jobs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import autospine_workbench.p10_spine42_v3_runtime_job_store_v2 as store_module
from autospine_workbench.p10_spine42_v3_runtime_job_store_v2 import (
    AUTHORIZATION_NAMESPACE, JOB_NAMESPACE,
    P10Spine42V3RuntimeJobStoreV2,
    P10Spine42V3RuntimeJobStoreV2Error,
)
from autospine_workbench.p10_spine42_v3_runtime_job_staging_v2 import (
    STAGING_NAMESPACE, create_runtime_job_staging_v2,
)
from tests.test_p10_spine42_v3_runtime_job_contract_v2 import _address, _sha
from tests.test_p10_spine42_v3_runtime_job_store_v2 import (
    _append, _reach, _request,
)


class P10Spine42V3RuntimeJobStoreAdversarialV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = P10Spine42V3RuntimeJobStoreV2(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_concurrent_duplicate_create_converges_without_duplicate_event(self):
        request = _request()
        stores = [P10Spine42V3RuntimeJobStoreV2(self.root) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda item: item.create(request), stores))
        self.assertEqual({request.job_id}, {row.job_id for row in rows})
        snapshot = self.store.load(request.job_id)
        self.assertEqual(1, len(snapshot.events))
        self.assertEqual("queued", snapshot.status)

    def test_concurrent_subject_and_retry_forks_have_one_winner(self):
        roots = [_request(), _request(authorization_id="auth-00000002")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.store.create, item) for item in roots]
        results = [future.exception() or future.result() for future in futures]
        self.assertEqual(1, sum(not isinstance(
            item, Exception) for item in results))
        first = next(item for item in results if not isinstance(item, Exception))
        first = _reach(self.store, first.request, "capturing")
        first = self.store.append_event(
            first.job_id, "failed_retryable", "capturing",
            expected_previous_event_sha256=first.head_event_sha256,
            failure_code="browser_failed", resume_mode="new_authorization")
        retries = [_request(authorization_id=f"auth-0000000{index}",
                            retry_of_job_id=first.job_id)
                   for index in (3, 4)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.store.create, item) for item in retries]
        results = [future.exception() or future.result() for future in futures]
        self.assertEqual(1, sum(not isinstance(
            item, Exception) for item in results))

    def test_request_and_event_inventory_tamper_fail_closed(self):
        row = self.store.create(_request())
        directory = self.root / "jobs" / JOB_NAMESPACE / row.job_id
        request_path = directory / "request.json"
        request_path.rename(directory / "Request.json")
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(row.job_id)
        (directory / "Request.json").rename(request_path)
        events = directory / "events"
        (events / "000001.json").rename(events / "000002.json")
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(row.job_id)
        (events / "000002.json").rename(events / "000001.json")
        (events / "extra.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(row.job_id)
        (events / "extra.json").unlink()
        (directory / "unexpected.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(row.job_id)

    def test_missing_artifacts_and_temporary_event_fail_closed(self):
        request_missing = self.store.create(_request())
        root = self.root / "jobs" / JOB_NAMESPACE
        (root / request_missing.job_id / "request.json").unlink()
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(request_missing.job_id)
        events_missing = self.store.create(_request(
            candidate_id=_sha("6"), entry_sha256=_sha("7"),
            authorization_id="auth-00000002"))
        events = root / events_missing.job_id / "events"
        events.rename(self.root / "removed-events")
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(events_missing.job_id)
        temporary = self.store.create(_request(
            candidate_id=_sha("7"), entry_sha256=_sha("8"),
            authorization_id="auth-00000003"))
        events = root / temporary.job_id / "events"
        (events / ".deadbeef.tmp").write_text("partial", encoding="utf-8")
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(temporary.job_id)

    def test_initial_publication_failures_leave_no_committed_run(self):
        real_publish = store_module.publish_json
        for failing_call in (1, 2):
            with self.subTest(failing_call=failing_call):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    store = P10Spine42V3RuntimeJobStoreV2(root)
                    request = _request()
                    calls = 0

                    def fail_once(*args, **kwargs):
                        nonlocal calls
                        calls += 1
                        if calls == failing_call:
                            raise RuntimeError("private publication failure")
                        return real_publish(*args, **kwargs)

                    with patch.object(store_module, "publish_json",
                                      side_effect=fail_once):
                        with self.assertRaises(
                            P10Spine42V3RuntimeJobStoreV2Error
                        ) as raised:
                            store.create(request)
                    self.assertNotIn("private", str(raised.exception).lower())
                    final = root / "jobs" / JOB_NAMESPACE / request.job_id
                    self.assertFalse(final.exists())
                    self.assertEqual(
                        (), store.recover_interrupted().interrupted_job_ids)
                    self.assertEqual("queued", store.create(request).status)

    def test_commit_failure_is_idempotently_repairable(self):
        request = _request()
        with patch.object(
            store_module, "commit_runtime_job_staging_v2",
            side_effect=RuntimeError("private commit failure"),
        ):
            with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
                self.store.create(request)
        final = self.root / "jobs" / JOB_NAMESPACE / request.job_id
        self.assertFalse(final.exists())
        recovery = self.store.recover_interrupted()
        self.assertEqual((), recovery.interrupted_job_ids)
        self.assertEqual((), recovery.readback_required_job_ids)
        repaired = self.store.create(request)
        self.assertEqual("queued", repaired.status)
        self.assertEqual(1, len(repaired.events))

    def test_restart_recovers_bound_stage_without_old_authorization_nonce(self):
        request = _request()
        with patch.object(
            store_module, "commit_runtime_job_staging_v2",
            side_effect=RuntimeError("simulated process exit"),
        ), patch.object(
            store_module, "cleanup_runtime_job_staging_v2",
            return_value=None,
        ):
            with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
                self.store.create(request)
        final = self.root / "jobs" / JOB_NAMESPACE / request.job_id
        staging = self.root / "jobs" / STAGING_NAMESPACE
        self.assertFalse(final.exists())
        self.assertEqual(1, sum(item.is_dir() for item in staging.iterdir()))
        temporary = staging / f".{_sha('a')[:12]}.abcdef.tmp"
        temporary.write_text("orphan", encoding="utf-8")

        restarted = P10Spine42V3RuntimeJobStoreV2(self.root)
        recovery = restarted.recover_interrupted()
        self.assertEqual((request.job_id,), recovery.interrupted_job_ids)
        recovered = restarted.load(request.job_id)
        self.assertEqual("interrupted_retryable", recovered.status)
        self.assertEqual("new_authorization", recovered.head["resume_mode"])
        self.assertFalse(recovered.public_document()[
            "runner_execution_authorized"])
        self.assertFalse(temporary.exists())
        retry = _request(authorization_id="auth-00000002",
                         retry_of_job_id=request.job_id)
        self.assertEqual("queued", restarted.create(retry).status)

    def test_restart_discards_only_validated_unbound_partial_staging(self):
        parent, staging = create_runtime_job_staging_v2(
            self.root, _request().job_id)
        temporary = parent / f".{_sha('b')[:12]}.abcdef.tmp"
        temporary.write_text("partial", encoding="utf-8")
        recovery = self.store.recover_interrupted()
        self.assertEqual((), recovery.interrupted_job_ids)
        self.assertFalse(staging.exists())
        self.assertFalse(temporary.exists())

    def test_alias_event_inventory_fails_closed_when_supported(self):
        row = self.store.create(_request())
        events = self.root / "jobs" / JOB_NAMESPACE / row.job_id / "events"
        alias = events / "000002.json"
        try:
            os.symlink(events / "000001.json", alias)
        except OSError:
            self.skipTest("symlink creation is unavailable")
        try:
            with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
                self.store.load(row.job_id)
        finally:
            alias.unlink(missing_ok=True)

    def test_binding_tamper_or_removal_never_repairs_on_load(self):
        row = self.store.create(_request())
        auth_root = self.root / "jobs" / AUTHORIZATION_NAMESPACE
        auth_file = next(auth_root.iterdir())
        document = json.loads(auth_file.read_text(encoding="utf-8"))
        document["format_version"] = 2.0
        auth_file.write_text(json.dumps(
            document, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(row.job_id)
        document["format_version"] = 2
        document["job_id"] = _sha("9")
        auth_file.write_text(json.dumps(
            document, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(row.job_id)
        auth_file.unlink()
        before = tuple(auth_root.iterdir())
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(row.job_id)
        self.assertEqual(before, tuple(auth_root.iterdir()))
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.create(_request())
        self.assertEqual(before, tuple(auth_root.iterdir()))

    def test_zero_event_final_is_tamper_and_recovery_fails_closed(self):
        row = self.store.create(_request())
        events = self.root / "jobs" / JOB_NAMESPACE / row.job_id / "events"
        (events / "000001.json").unlink()
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.recover_interrupted()

    def test_load_replay_rejects_a_chain_sealed_to_another_source(self):
        row = _reach(self.store, _request(), "evidence_compiling")
        address = _address(); address["project_id"] = "other"
        with patch.object(store_module, "require_runtime_job_source_binding_v2",
                          return_value=None):
            row = _append(self.store, row, "publishing", address=address)
            row = _append(self.store, row, "parent_exact_readback",
                          address=address)
            row = self.store.append_event(
                row.job_id, "completed", "completed",
                expected_previous_event_sha256=row.head_event_sha256,
                current=1, total=1, result=address)
        self.assertEqual("completed", row.status)
        with self.assertRaises(P10Spine42V3RuntimeJobStoreV2Error):
            self.store.load(row.job_id)


if __name__ == "__main__":
    unittest.main()
