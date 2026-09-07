"""Exact journal/authority fixture with simulated P10.7b execution edges."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from autospine_workbench.p10_spine42_v3_runtime_authority_v2 import (
    P10Spine42V3RuntimeAuthorityV2,
)
from autospine_workbench.p10_spine42_v3_runtime_job_store_v2 import (
    P10Spine42V3RuntimeJobStoreV2,
)
from autospine_workbench.p10_spine42_v3_runtime_manager_owner_lease_v2 import (
    P10Spine42V3RuntimeManagerOwnerLeaseV2,
)
from autospine_workbench.p10_spine42_v3_runtime_preflight_v2 import (
    P10Spine42V3RuntimePreflightV2,
)
from autospine_workbench.spine42_v3_runtime_bundle_v2 import (
    Spine42V3RuntimeBundleV2,
)
from tests.p10_spine42_v3_runtime_preflight_v2_support import BridgeFactory


class ExecutionV2Fixture:
    def __init__(self, state_root: Path, source_fixture):
        self.state_root = state_root
        state_root.mkdir()
        self.source_fixture = source_fixture
        self.preflight = P10Spine42V3RuntimePreflightV2(
            state_root,
            candidate_revalidator=lambda *_: source_fixture.candidate,
            catalog_reader=lambda *_: source_fixture.catalog(),
            bridge_factory=BridgeFactory(source_fixture),
            environment_discovery=lambda *_: source_fixture.environment,
        )
        prepared = self.preflight.prepare(
            source_fixture.payload(), selection_source="automatic",
        )
        self.ready = self.preflight.refresh_for_create(prepared)
        self.store = P10Spine42V3RuntimeJobStoreV2(state_root)
        queued = self.store.create(self.ready.request)
        self.claimed = self.store.append_event(
            queued.job_id, "running", "exact_source_readback",
            expected_previous_event_sha256=queued.head_event_sha256,
        )
        self.lease = P10Spine42V3RuntimeManagerOwnerLeaseV2(
            state_root).acquire()
        self.authority = P10Spine42V3RuntimeAuthorityV2(
            self.store, self.lease)
        self.permit = self.authority.issue(self.ready, self.claimed)
        source = self.ready.request.document["source"]
        self.bundle = Spine42V3RuntimeBundleV2(
            source["project_id"], source["clip_id"],
            source["skeleton_json_sha256"],
            source["spine42_v3_bundle_sha256"], "e" * 64,
            "f" * 64, (),
        )
        self.run = object()
        self.evidence = object()

    @property
    def address(self):
        bundle = self.bundle
        return {
            "project_id": bundle.project_id,
            "skeleton_json_sha256": bundle.skeleton_json_sha256,
            "spine42_v3_bundle_sha256": bundle.spine42_v3_bundle_sha256,
            "capture_bundle_sha256": bundle.bundle_sha256,
        }

    def dependencies(self, *, runner=None, publisher=None, readback=None,
                     evidence_builder=None, bundle_builder=None):
        publisher = publisher or PublishBoundary()
        return {
            "runner": runner or Mock(return_value=self.run),
            "evidence_builder": evidence_builder or Mock(
                return_value=self.evidence),
            "bundle_builder": bundle_builder or Mock(
                return_value=self.bundle),
            "publisher_factory": publisher,
            "reader_factory": lambda _root: object(),
            "readback": readback or Mock(return_value=self.address),
        }

    def close(self):
        self.lease.close()


class PublishBoundary:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []

    def __call__(self, state_root):
        self.state_root = state_root
        return self

    def publish(self, evidence):
        self.calls.append(evidence)
        if self.failure is not None:
            raise self.failure
        return object()


__all__ = ["ExecutionV2Fixture", "PublishBoundary"]
