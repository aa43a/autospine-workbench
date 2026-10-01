"""Concurrent reads retain complete byte validation and no completed-result trust."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock, get_ident
import unittest
from unittest.mock import patch

from autospine_workbench.automation import _animated_read_cohort as cohorts
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes, read_document


class AnimatedReadCohortTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.files = {"skeleton.json": b"{}", "skeleton.atlas": b"page.png\n",
                      "page.png": b"png", "editor/unused.png": b"original"}
        self.store = AnimatedStore(self.root)
        self.digest = self.store.publish(self.files)
        self.folder = self.store.root / self.digest
        self.registry = cohorts.ReadCohorts()
        patched = patch.object(cohorts, "_COHORTS", self.registry)
        patched.start()
        self.addCleanup(patched.stop)

    def assert_empty(self):
        self.assertEqual(self.registry._preparing, {})
        self.assertEqual(self.registry._active, 0)
        self.assertEqual(self.registry._bytes, 0)

    def batch(self, count=4):
        """Hold only manifest/path preparation so all members precede byte IO."""
        entered, release, followers = Event(), Event(), Event()
        guard, started, ready = Lock(), 0, 0
        original = cohorts.prepare

        def prepare(*args):
            nonlocal started, ready
            with guard:
                started += 1
                leader = started == 1
            if leader:
                entered.set()
                self.assertTrue(release.wait(5))
            try:
                return original(*args)
            finally:
                if not leader:
                    with guard:
                        ready += 1
                        if ready == count - 1:
                            followers.set()

        with patch.object(cohorts, "prepare", side_effect=prepare), ThreadPoolExecutor(count) as pool:
            first = pool.submit(self.store.read, self.digest)
            self.assertTrue(entered.wait(5))
            remaining = [pool.submit(self.store.read, self.digest) for _ in range(count - 1)]
            try:
                self.assertTrue(followers.wait(5))
            finally:
                release.set()
            futures = [first, *remaining]
            return futures

    def test_one_complete_pass_for_presealed_batch_and_isolated_containers(self):
        with patch.object(cohorts, "verify", wraps=cohorts.verify) as verified:
            results = [future.result() for future in self.batch()]
        self.assertEqual(verified.call_count, 1)
        self.assertTrue(all(type(result) is dict and result == self.files for result in results))
        self.assertTrue(all(type(raw) is bytes for result in results for raw in result.values()))
        self.assertIs(results[0]["page.png"], results[1]["page.png"])
        results[0]["page.png"] = b"caller change"
        self.assertEqual(results[1], self.files)
        self.assert_empty()

    def test_late_caller_reads_complete_bytes_before_first_cohort_finishes(self):
        entered, release = Event(), Event()
        guard, calls = Lock(), 0
        original = cohorts.verify

        def verify(*args):
            nonlocal calls
            with guard:
                calls += 1
                first = calls == 1
            if first:
                entered.set()
                self.assertTrue(release.wait(5))
            return original(*args)

        with patch.object(cohorts, "verify", side_effect=verify), ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.store.read, self.digest)
            self.assertTrue(entered.wait(5))
            late = pool.submit(self.store.read, self.digest)
            try:
                self.assertEqual(late.result(5), self.files)
            finally:
                release.set()
            self.assertEqual(first.result(5), self.files)
        self.assertEqual(calls, 2)
        self.assert_empty()

    def test_sequential_calls_always_reverify_and_unused_corruption_fails(self):
        with patch.object(cohorts, "verify", wraps=cohorts.verify) as verified:
            self.assertEqual(self.store.read(self.digest), self.files)
            self.assertEqual(self.store.read(self.digest), self.files)
            self.assertEqual(verified.call_count, 2)
        (self.folder / "editor/unused.png").write_bytes(b"modified")
        with self.assertRaisesRegex(PipelineRunError, "artifact_invalid"):
            self.store.read(self.digest)
        # The separate addressed-file API retains its existing narrower contract.
        self.assertEqual(self.store.read_file(self.digest, "skeleton.json"), b"{}")
        self.assert_empty()

    def test_changed_manifest_after_content_read_is_rejected(self):
        original = cohorts.read_real_file
        changed = False

        def read(*args):
            nonlocal changed
            raw = original(*args)
            if not changed:
                changed = True
                inventory = read_document(self.folder / "inventory.json")
                inventory["page.png"] = sha256(b"different").hexdigest()
                (self.folder / "inventory.json").write_bytes(canonical_bytes(inventory))
            return raw

        with patch.object(cohorts, "read_real_file", side_effect=read):
            with self.assertRaisesRegex(PipelineRunError, "artifact_invalid"):
                self.store.read(self.digest)
        self.assert_empty()

    def test_replacing_an_already_read_file_is_rejected_at_the_end(self):
        original = cohorts.read_real_file
        changed = False

        def read(file, *args):
            nonlocal changed
            raw = original(file, *args)
            if not changed:
                changed = True
                file.write_bytes(b"modified after verified read")
            return raw

        with patch.object(cohorts, "read_real_file", side_effect=read):
            with self.assertRaisesRegex(PipelineRunError, "artifact_invalid"):
                self.store.read(self.digest)
        self.assert_empty()

    def test_extra_file_and_hard_link_are_rejected_before_content_read(self):
        for linked in (False, True):
            extra = self.folder / "extra.png"
            if linked:
                extra.hardlink_to(self.folder / "page.png")
            else:
                extra.write_bytes(b"extra")
            try:
                with patch.object(cohorts, "read_real_file", wraps=cohorts.read_real_file) as read:
                    with self.assertRaisesRegex(PipelineRunError, "artifact_invalid"):
                        self.store.read(self.digest)
                    read.assert_not_called()
            finally:
                extra.unlink()
        self.assertEqual(self.store.read(self.digest), self.files)
        self.assert_empty()

    def test_declared_file_hard_link_and_manifest_hard_link_fail_closed(self):
        for name in ("page.png", "inventory.json"):
            linked = self.root / "outside-link"
            linked.hardlink_to(self.folder / name)
            try:
                with self.assertRaisesRegex(PipelineRunError, "artifact_invalid"):
                    self.store.read(self.digest)
            finally:
                linked.unlink()
        self.assert_empty()

    def test_failure_reaches_whole_cohort_as_separate_errors_and_retry_is_fresh(self):
        with patch.object(cohorts, "verify", side_effect=PipelineRunError("injected_failure")) as verified:
            futures = self.batch()
            errors = [future.exception() for future in futures]
        self.assertEqual(verified.call_count, 1)
        self.assertTrue(all(str(error) == "injected_failure" for error in errors))
        self.assertEqual(len({id(error) for error in errors}), len(errors))
        self.assert_empty()
        self.assertEqual(self.store.read(self.digest), self.files)

    def test_same_digest_in_independent_roots_never_shares(self):
        other = AnimatedStore(self.root / "other")
        self.assertEqual(other.publish(self.files), self.digest)
        rendezvous = Barrier(2)
        original = cohorts.prepare

        def prepare(*args):
            rendezvous.wait(5)
            return original(*args)

        with patch.object(cohorts, "prepare", side_effect=prepare), \
                patch.object(cohorts, "verify", wraps=cohorts.verify) as verified, \
                ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(store.read, self.digest) for store in (self.store, other)]
            self.assertTrue(all(future.result(5) == self.files for future in futures))
        self.assertEqual(verified.call_count, 2)
        self.assert_empty()

    def test_nested_publish_does_not_self_wait_and_releases_the_flight(self):
        original = cohorts.verify

        def verify(*args):
            self.store.publish(self.files)
            return original(*args)

        with patch.object(cohorts, "verify", side_effect=verify), ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.store.read, self.digest)
            with self.assertRaisesRegex(PipelineRunError, "animated_read_reentrant"):
                future.result(5)
        self.assert_empty()
        self.assertEqual(self.store.read(self.digest), self.files)

    def test_preflight_limits_precede_all_candidate_content_reads(self):
        with patch("autospine_workbench.automation.animated_store.MAX_TOTAL", 1), \
                patch.object(cohorts, "read_real_file", wraps=cohorts.read_real_file) as read:
            with self.assertRaisesRegex(PipelineRunError, "animated_resource_limit"):
                self.store.read(self.digest)
            read.assert_not_called()
        self.assert_empty()

    def test_empty_publisher_staging_and_declared_staging_files_are_compatible(self):
        self.assertTrue((self.folder / "staging").is_dir())
        self.assertEqual(self.store.read(self.digest), self.files)
        declared = {**self.files, "staging/declared.png": b"declared"}
        self.assertEqual(self.store.read(self.store.publish(declared)), declared)
        extra = self.folder / "staging/pending-undeclared"
        extra.write_bytes(b"unfinished publisher")
        try:
            with self.assertRaisesRegex(PipelineRunError, "artifact_invalid"):
                self.store.read(self.digest)
        finally:
            extra.unlink()
        self.assertEqual(self.store.read(self.digest), self.files)
        self.assert_empty()

    def test_single_flight_budget_queues_late_caller_for_its_own_pass(self):
        self.registry.max_flights = 1
        entered, late_started, queued, release = Event(), Event(), Event(), Event()
        original_verify, original_wait = cohorts.verify, self.registry._condition.wait
        calls = 0

        def verify(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                self.assertTrue(release.wait(5))
            return original_verify(*args)

        def wait(*args, **kwargs):
            if late_started.is_set():
                queued.set()
            return original_wait(*args, **kwargs)

        def late_read():
            late_started.set()
            return self.store.read(self.digest)

        with patch.object(cohorts, "verify", side_effect=verify), \
                patch.object(self.registry._condition, "wait", side_effect=wait), \
                ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.store.read, self.digest)
            self.assertTrue(entered.wait(5))
            late = pool.submit(late_read)
            try:
                self.assertTrue(queued.wait(5))
                self.assertEqual(self.registry._active, 1)
            finally:
                release.set()
            self.assertEqual(first.result(5), self.files)
            self.assertEqual(late.result(5), self.files)
        self.assertEqual(calls, 2)
        self.assert_empty()

    def test_follower_preflight_failure_stops_every_content_read(self):
        original = cohorts.prepare
        guard, count = Lock(), 0

        def prepare(*args):
            nonlocal count
            plan = original(*args)
            with guard:
                count += 1
                fail = count == 1
            if fail:
                raise PipelineRunError("injected_preflight_failure")
            return plan

        with patch.object(cohorts, "prepare", side_effect=prepare), \
                patch.object(cohorts, "verify", wraps=cohorts.verify) as verified:
            futures = self.batch()
        self.assertTrue(all(str(future.exception()) == "injected_preflight_failure" for future in futures))
        verified.assert_not_called()
        self.assert_empty()
        self.assertEqual(self.store.read(self.digest), self.files)

    def test_leader_wait_error_cleans_up_and_reaches_waiting_member(self):
        leader_ready, follower_ready, leader_release, follower_release = Event(), Event(), Event(), Event()
        original_prepare, original_wait = cohorts.prepare, self.registry._condition.wait
        guard, count, leader_thread = Lock(), 0, None

        def prepare(*args):
            nonlocal count, leader_thread
            with guard:
                count += 1
                leader = count == 1
            if leader:
                leader_thread = get_ident()
                leader_ready.set()
                self.assertTrue(leader_release.wait(5))
            else:
                follower_ready.set()
                self.assertTrue(follower_release.wait(5))
            return original_prepare(*args)

        def wait(*args, **kwargs):
            if get_ident() == leader_thread:
                raise RuntimeError("injected_wait_failure")
            return original_wait(*args, **kwargs)

        with patch.object(cohorts, "prepare", side_effect=prepare), \
                patch.object(self.registry._condition, "wait", side_effect=wait), \
                patch.object(cohorts, "verify", wraps=cohorts.verify) as verified, \
                ThreadPoolExecutor(2) as pool:
            leader = pool.submit(self.store.read, self.digest)
            self.assertTrue(leader_ready.wait(5))
            follower = pool.submit(self.store.read, self.digest)
            try:
                self.assertTrue(follower_ready.wait(5))
                leader_release.set()
                with self.assertRaisesRegex(RuntimeError, "injected_wait_failure"):
                    leader.result(5)
                self.assert_empty()
            finally:
                leader_release.set()
                follower_release.set()
            with self.assertRaisesRegex(RuntimeError, "injected_wait_failure"):
                follower.result(5)
        verified.assert_not_called()
        self.assert_empty()
        self.assertEqual(self.store.read(self.digest), self.files)

    def test_coordinator_rejects_unbounded_budget_configuration(self):
        for budget in (0, -1, True, "2"):
            with self.assertRaises(ValueError):
                cohorts.ReadCohorts(max_flights=budget)
        limited = cohorts.ReadCohorts(max_bytes=1)
        for reservation in (0, -1, True, "1", 2):
            with self.assertRaisesRegex(PipelineRunError, "animated_resource_limit"):
                limited.read("key", lambda: None, lambda _: {}, reservation=reservation)


if __name__ == "__main__":
    unittest.main()
