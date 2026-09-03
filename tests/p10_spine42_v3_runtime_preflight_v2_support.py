"""Issued fixtures shared by P10.7b v2 preflight and authority tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
)
from autospine_workbench.browser_version_identity import (
    browser_version_identity_sha256,
)
from autospine_workbench.p10_runtime_environment import P10RuntimeEnvironment
from autospine_workbench.p10_spine42_v3_job_contract_v2 import DOCUMENT_NAMES
from autospine_workbench.p10_spine42_v3_job_v2 import P10Spine42V3JobStoreV2
from autospine_workbench.spine42_v3_runtime_candidate_catalog_v2 import (
    Spine42V3RuntimeCandidateCatalogV2,
)
from autospine_workbench.spine42_v3_runtime_candidate_contract_v2 import (
    Spine42V3RuntimeCandidateV2,
)
from tests.p10_spine42_v3_runtime_candidate_support import inputs
from tests.test_spine42_v3_runtime_capture_harness_v2 import V2HarnessFixture


def sha(character):
    return character * 64


class PreflightV2Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.harness = V2HarnessFixture(root / "harness")
        self.bundle, self.source = self.harness.bundle, self.harness.source
        runtime = replace(
            self.harness.runtime,
            package_json_sha256=sha("a"), license_sha256=sha("b"),
        )
        version = "140.0.7339.1"
        browser = BrowserExecutableSnapshot(
            str(root / "private" / "chrome.exe"), "chromium", version,
            browser_version_identity_sha256("chromium", version),
            sha("c"), 4096,
        )
        self.environment = P10RuntimeEnvironment(runtime, browser)
        self.candidate = self.make_candidate("d")

    def make_candidate(self, marker):
        state = self.root / f"candidate-{marker}"
        state.mkdir(exist_ok=True)
        store = P10Spine42V3JobStoreV2(state)
        row = store.create(
            inputs(project=self.bundle.project_id),
            attempt=1, previous_run_id=None,
        )
        for stage, current in (
            ("exact_motion_instance", 0), ("source_adapter", 0),
            ("spine_adapter", 0), ("publication", 1),
            ("parent_exact_readback", 0),
        ):
            row = store.append(
                row.run_id, "running", stage,
                expected_previous=row.head_sha256,
                current=current, total=1,
            )
        result = {
            "project_id": self.bundle.project_id,
            "clip_id": self.bundle.clip_id,
            "skeleton_json_sha256": self.bundle.skeleton_json_sha256,
            "bundle_sha256": self.bundle.bundle_sha256,
            "run_document_sha256": sha(marker),
            "report_sha256": sha("e"),
            "inventory": list(DOCUMENT_NAMES), "reused": False,
        }
        row = store.append(
            row.run_id, "completed", "completed",
            expected_previous=row.head_sha256,
            current=1, total=1, result=result,
        )
        return Spine42V3RuntimeCandidateV2.from_completed_head(row)

    def payload(self, **changes):
        row = {
            "candidate_id": self.candidate.candidate_id,
            "entry_sha256": self.candidate.entry_sha256,
            "authorization_id": "auth-automatic-0001",
            "retry_of_job_id": None,
            "explicit_runtime_license_confirmation": True,
            "explicit_run_confirmation": True,
        }
        row.update(changes)
        return row

    def catalog(self, mode="automatic", candidate=None):
        selected = candidate or self.candidate
        recommended = selected if mode == "automatic" else None
        return Spine42V3RuntimeCandidateCatalogV2(
            (selected,), (), (), 1,
            {
                "mode": mode,
                "reason_code": "unique_eligible_candidate"
                if mode == "automatic" else "multiple_candidates",
                "requested_spine_run_id": None,
                "recommended_candidate_id": None if recommended is None
                else recommended.candidate_id,
                "recommended_entry_sha256": None if recommended is None
                else recommended.entry_sha256,
            },
        )


class BridgeFactory:
    def __init__(self, fixture):
        self.fixture = fixture
        self.build_calls = []
        self.rebuild_calls = []

    def __call__(self, state_root):
        return self

    def build(self, project_id, skeleton_json_sha256, bundle_sha256):
        self.build_calls.append(
            (project_id, skeleton_json_sha256, bundle_sha256)
        )
        return self.fixture.source

    def rebuild_and_verify(self, expected):
        self.rebuild_calls.append(expected)
        if expected is not self.fixture.source:
            raise RuntimeError("unexpected source")
        return expected


__all__ = ["BridgeFactory", "PreflightV2Fixture", "sha"]
