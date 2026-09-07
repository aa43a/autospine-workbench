"""Immutable journal, CAS and execution lease integration tests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from tests.test_pipeline_run import ADDRESSES, ROOT
from autospine_workbench.automation.pipeline_run import PipelineRunError, seal
from autospine_workbench.automation.pipeline_run_store import PipelineRunStore, PipelineConflict
from autospine_workbench.automation.pipeline_lease import execution_lease
from autospine_workbench.automation.storage_io import canonical_bytes


class PipelineRunStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = PipelineRunStore(self.root)
        self.run = self.store.create("sample-a", "production_review", ADDRESSES)
        self.events = self.store.root / self.run["run_id"] / "events"

    def append(self, source, action, **kwargs):
        return self.store.append(source["run_id"], source["state_sha256"], action, **kwargs)

    def test_create_is_idempotent_and_reopen_returns_latest_without_overwrite(self):
        running = self.append(self.run, "start")
        original = (self.events / "000000.json").read_bytes()
        same = self.store.create("sample-a", "production_review", ADDRESSES)
        self.assertEqual(same, running)
        self.assertEqual(original, (self.events / "000000.json").read_bytes())
        reopened = PipelineRunStore(self.root).load(self.run["run_id"])
        self.assertEqual(reopened, running)

    def test_stale_cas_does_not_append(self):
        running = self.append(self.run, "start")
        with self.assertRaises(PipelineConflict):
            self.append(self.run, "cancel")
        self.assertEqual(self.store.load(self.run["run_id"]), running)
        self.assertEqual(len(list(self.events.iterdir())), 2)

    def test_concurrent_append_has_one_winner(self):
        load = self.store.load
        barrier = Barrier(2)

        def synchronized_load(run_id):
            result = load(run_id)
            barrier.wait(timeout=10)
            return result

        def worker(action):
            try:
                return self.append(self.run, action)
            except PipelineConflict:
                return None

        with patch.object(self.store, "load", synchronized_load):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(worker, ("start", "cancel")))
        winner = [result for result in results if result is not None]
        self.assertEqual(len(winner), 1)
        self.assertEqual(self.store.load(self.run["run_id"]), winner[0])
        self.assertEqual(list((self.events.parent / "staging").iterdir()), [])

    def test_changed_content_and_resealed_transition_both_fail_closed(self):
        running = self.append(self.run, "start")
        path = self.events / "000001.json"
        invalid = deepcopy(running)
        invalid["status"] = "pending"
        path.write_bytes(canonical_bytes(invalid))
        with self.assertRaises(PipelineRunError):
            self.store.load(self.run["run_id"])
        invalid = seal({**running, "action": "resume"})
        path.write_bytes(canonical_bytes(invalid))
        with self.assertRaises(PipelineRunError):
            self.store.load(self.run["run_id"])

    def test_missing_middle_revision_and_unrecognized_event_fail_closed(self):
        running = self.append(self.run, "start")
        self.append(running, "resume")
        middle = self.events / "000001.json"
        saved = middle.read_bytes()
        middle.unlink()
        with self.assertRaises(PipelineRunError) as caught:
            self.store.load(self.run["run_id"])
        self.assertEqual(caught.exception.reason_code, "pipeline_history_invalid")
        middle.write_bytes(saved)
        (self.events / "notes.txt").write_text("unexpected")
        with self.assertRaises(PipelineRunError):
            self.store.load(self.run["run_id"])

    def test_noncanonical_or_duplicate_key_json_is_rejected(self):
        path = self.events / "000000.json"
        path.write_text(json.dumps(self.run, indent=2), encoding="utf-8")
        with self.assertRaises(PipelineRunError):
            self.store.load(self.run["run_id"])
        raw = canonical_bytes(self.run)
        path.write_bytes(b'{"authority":"release",' + raw[1:])
        with self.assertRaises(PipelineRunError):
            self.store.load(self.run["run_id"])

    def test_empty_journal_and_missing_run_fail_closed(self):
        (self.events / "000000.json").unlink()
        with self.assertRaises(PipelineRunError):
            self.store.load(self.run["run_id"])
        with self.assertRaises(PipelineRunError) as caught:
            self.store.load("run-" + "f" * 64)
        self.assertEqual(caught.exception.reason_code, "pipeline_run_not_found")

    def test_invalid_run_path_cannot_escape_store(self):
        for run_id in ("../outside", "run-" + "a" * 64 + "/file", "run-CON"):
            with self.subTest(run_id=run_id), self.assertRaises(PipelineRunError):
                self.store.load(run_id)

    def test_execution_lease_reentry_fails_and_release_allows_retry(self):
        run_id = self.run["run_id"]
        with execution_lease(self.root, run_id):
            with self.assertRaises(PipelineRunError) as caught:
                with execution_lease(self.root, run_id):
                    self.fail("lease is reentrant")
            self.assertEqual(caught.exception.reason_code, "pipeline_run_busy")
        with execution_lease(self.root, run_id):
            pass

    def test_execution_lease_releases_after_consumer_exception(self):
        run_id = self.run["run_id"]
        with self.assertRaisesRegex(ValueError, "worker failed"):
            with execution_lease(self.root, run_id):
                raise ValueError("worker failed")
        with execution_lease(self.root, run_id):
            pass

    def test_different_run_lease_is_independent(self):
        with execution_lease(self.root, self.run["run_id"]):
            with execution_lease(self.root, "run-" + "a" * 64):
                pass

    def test_execution_lease_is_released_by_os_after_worker_crash(self):
        script = (
            "import os,sys; "
            "from autospine_workbench.automation.pipeline_lease import execution_lease; "
            "lease=execution_lease(sys.argv[1],sys.argv[2]); "
            "lease.__enter__(); os._exit(17)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.root), self.run["run_id"]],
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 17, result.stderr.decode(errors="replace"))
        with execution_lease(self.root, self.run["run_id"]):
            pass

    def test_hardlinked_lease_file_is_rejected(self):
        run_id = self.run["run_id"]
        with execution_lease(self.root, run_id):
            pass
        lock = self.root / "jobs/pipeline-execution-v1" / run_id / "owner.lock"
        try:
            os.link(lock, self.root / "lock-alias")
        except OSError:
            self.skipTest("hard links unavailable")
        with self.assertRaises(PipelineRunError) as caught:
            with execution_lease(self.root, run_id):
                self.fail("hardlinked lock acquired")
        self.assertEqual(caught.exception.reason_code, "pipeline_storage_invalid")


if __name__ == "__main__":
    unittest.main()
