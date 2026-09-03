"""In-memory one-shot execution authority tests for P10.7b v2."""

from __future__ import annotations

import copy
from pathlib import Path
import pickle
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_spine42_v3_runtime_authority_v2 import (  # noqa: E402
    P10Spine42V3RuntimeAuthorityV2,
    P10Spine42V3RuntimeAuthorityV2Error,
)
from autospine_workbench.p10_spine42_v3_runtime_job_store_v2 import (  # noqa: E402
    P10Spine42V3RuntimeJobStoreV2,
)
from autospine_workbench.p10_spine42_v3_runtime_manager_owner_lease_v2 import (  # noqa: E402
    P10Spine42V3RuntimeManagerOwnerLeaseV2,
)
from autospine_workbench.p10_spine42_v3_runtime_preflight_v2 import (  # noqa: E402
    P10Spine42V3RuntimePreflightV2,
)
from tests.p10_spine42_v3_runtime_preflight_v2_support import (  # noqa: E402
    BridgeFactory, PreflightV2Fixture,
)


class P10Spine42V3RuntimeAuthorityV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = PreflightV2Fixture(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.state = self.root / self._testMethodName
        self.state.mkdir()
        fixture = self.fixture
        self.preflight = P10Spine42V3RuntimePreflightV2(
            self.state,
            candidate_revalidator=lambda *_: fixture.candidate,
            catalog_reader=lambda *_: fixture.catalog(),
            bridge_factory=BridgeFactory(fixture),
            environment_discovery=lambda *_: fixture.environment,
        )
        self.initial = self.preflight.prepare(
            fixture.payload(), selection_source="automatic",
        )
        self.prepared = self.preflight.refresh_for_create(self.initial)
        self.store = P10Spine42V3RuntimeJobStoreV2(self.state)
        self.queued = self.store.create(self.prepared.request)
        self.claimed = self.store.append_event(
            self.queued.job_id, "running", "exact_source_readback",
            expected_previous_event_sha256=self.queued.head_event_sha256,
        )
        self.lease = P10Spine42V3RuntimeManagerOwnerLeaseV2(
            self.state).acquire()
        self.authority = P10Spine42V3RuntimeAuthorityV2(
            self.store, self.lease)

    def tearDown(self):
        self.lease.close()

    def test_exact_persisted_cas_claim_issues_one_bound_permit(self):
        permit = self.authority.issue(self.prepared, self.claimed)
        self.assertEqual(self.claimed.job_id, permit.job_id)
        self.assertEqual(self.claimed.head_event_sha256,
                         permit.head_event_sha256)
        self.assertNotIn(str(self.root), repr(permit))
        context = self.authority.consume(permit)
        self.assertIs(self.prepared, context.prepared)
        self.assertIs(self.prepared.request, context.request)
        self.assertIs(self.fixture.candidate, context.candidate)
        self.assertIs(self.fixture.source, context.source)
        self.assertIs(self.fixture.environment.runtime, context.runtime)
        self.assertIs(self.fixture.environment.browser, context.browser)
        self.assertNotIn(str(self.root), repr(context))
        refreshed = self.preflight.refresh_for_execution(context.prepared)
        self.assertEqual("automatic", refreshed.selection_source)
        self.assertEqual(
            context.request.canonical_bytes, refreshed.request.canonical_bytes,
        )
        for operation in (
            lambda: copy.copy(context), lambda: copy.deepcopy(context),
            lambda: pickle.dumps(context),
        ):
            with self.assertRaises(TypeError):
                operation()
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            self.authority.consume(permit)

    def test_permit_cannot_be_duplicated_forged_or_serialized(self):
        permit = self.authority.issue(self.prepared, self.claimed)
        for operation in (
            lambda: copy.copy(permit), lambda: copy.deepcopy(permit),
            lambda: pickle.dumps(permit),
        ):
            with self.subTest(operation=operation), self.assertRaises(
                (TypeError, P10Spine42V3RuntimeAuthorityV2Error)
            ):
                operation()
        forged = object.__new__(type(permit))
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            self.authority.consume(forged)
        for value in (
            self.claimed.public_document(),
            self.claimed.request.document["authorization_id"],
            self.claimed.request.document,
        ):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                P10Spine42V3RuntimeAuthorityV2Error
            ):
                self.authority.consume(value)

    def test_queued_stale_or_duplicate_claim_never_issues(self):
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            self.authority.issue(self.prepared, self.queued)
        permit = self.authority.issue(self.prepared, self.claimed)
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            self.authority.issue(self.prepared, self.claimed)
        advanced = self.store.append_event(
            self.claimed.job_id, "running", "runtime_reverified",
            expected_previous_event_sha256=self.claimed.head_event_sha256,
        )
        self.assertEqual("runtime_reverified", advanced.head["stage"])
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            self.authority.consume(permit)

    def test_two_authorities_under_one_owner_cannot_issue_same_claim(self):
        other = P10Spine42V3RuntimeAuthorityV2(
            self.store, self.lease)
        permit = self.authority.issue(self.prepared, self.claimed)
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            other.issue(self.prepared, self.claimed)
        self.authority.revoke(permit)

    def test_closed_or_reacquired_owner_cannot_consume_old_permit(self):
        permit = self.authority.issue(self.prepared, self.claimed)
        self.lease.close()
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error) as caught:
            self.authority.consume(permit)
        self.assertNotIn(str(self.root), str(caught.exception))
        self.lease.acquire()
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            self.authority.consume(permit)

    def test_same_job_and_head_are_independent_across_state_roots(self):
        other_root = self.root / f"{self._testMethodName}-other"
        other_root.mkdir()
        fixture = self.fixture
        other_preflight = P10Spine42V3RuntimePreflightV2(
            other_root,
            candidate_revalidator=lambda *_: fixture.candidate,
            catalog_reader=lambda *_: fixture.catalog(),
            bridge_factory=BridgeFactory(fixture),
            environment_discovery=lambda *_: fixture.environment,
        )
        other_initial = other_preflight.prepare(
            fixture.payload(), selection_source="automatic",
        )
        other_prepared = other_preflight.refresh_for_create(other_initial)
        other_store = P10Spine42V3RuntimeJobStoreV2(other_root)
        other_queued = other_store.create(other_prepared.request)
        other_claimed = other_store.append_event(
            other_queued.job_id, "running", "exact_source_readback",
            expected_previous_event_sha256=other_queued.head_event_sha256,
        )
        self.assertEqual(self.claimed.job_id, other_claimed.job_id)
        self.assertEqual(
            self.claimed.head_event_sha256,
            other_claimed.head_event_sha256,
        )
        other_lease = P10Spine42V3RuntimeManagerOwnerLeaseV2(
            other_root).acquire()
        try:
            other = P10Spine42V3RuntimeAuthorityV2(
                other_store, other_lease)
            first = self.authority.issue(self.prepared, self.claimed)
            with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
                other.issue(self.prepared, other_claimed)
            second = other.issue(other_prepared, other_claimed)
            self.assertNotEqual(first, second)
        finally:
            other_lease.close()

    def test_initial_generation_and_cross_root_components_are_rejected(self):
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            self.authority.issue(self.initial, self.claimed)
        other_root = self.root / f"{self._testMethodName}-other"
        other_root.mkdir()
        other_store = P10Spine42V3RuntimeJobStoreV2(other_root)
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            P10Spine42V3RuntimeAuthorityV2(other_store, self.lease)

    def test_revoke_burns_permit_and_loader_failures_are_path_free(self):
        permit = self.authority.issue(self.prepared, self.claimed)
        self.assertTrue(self.authority.revoke(permit))
        self.assertFalse(self.authority.revoke(permit))
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error):
            self.authority.consume(permit)

        authority = P10Spine42V3RuntimeAuthorityV2(
            self.store, self.lease,
        )
        with self.assertRaises(P10Spine42V3RuntimeAuthorityV2Error) as caught:
            authority.issue(self.prepared, self.claimed)
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_constructor_requires_exact_current_owner_lease(self):
        closed_root = self.root / f"{self._testMethodName}-closed"
        closed_root.mkdir()
        closed = P10Spine42V3RuntimeManagerOwnerLeaseV2(
            closed_root)
        for value in (None, closed):
            with self.subTest(value=value), self.assertRaises(
                P10Spine42V3RuntimeAuthorityV2Error
            ) as caught:
                P10Spine42V3RuntimeAuthorityV2(self.store, value)
            self.assertNotIn(str(self.root), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
