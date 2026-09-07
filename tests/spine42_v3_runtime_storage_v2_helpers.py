"""Shared issued fixture for isolated P10.7b v2 storage tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
)
from autospine_workbench.browser_version_identity import (
    browser_version_identity_sha256,
)
from autospine_workbench.spine42_v3_runtime_bundle_v2 import (
    build_spine42_v3_runtime_bundle_v2,
)
from autospine_workbench.spine42_v3_runtime_evidence_v2 import (
    build_spine42_v3_runtime_evidence_v2,
)
from tests.spine42_v3_runtime_issued_run_v2_helpers import (
    issued_runtime_run_v2,
)
from tests.test_spine42_v3_runtime_capture_harness import _png
from tests.test_spine42_v3_runtime_capture_harness_v2 import (
    V2HarnessFixture, _fake_runtime_profile_v2,
)


class RuntimeStorageV2Fixture:
    def __init__(self, root: Path):
        self.harness = V2HarnessFixture(root / "upstream")
        self.upstream = self.harness.bundle
        self.state_root = self.harness.source_fixture.state_root
        runtime = replace(
            self.harness.runtime,
            package_json_sha256="a" * 64, license_sha256="b" * 64,
        )
        version = "128.0.6613.0"
        browser = BrowserExecutableSnapshot(
            str(root / "chrome.exe"), "chromium", version,
            browser_version_identity_sha256("chromium", version),
            "c" * 64, 4096,
        )
        self.runtime, self.browser = runtime, browser
        png = _png()
        with _fake_runtime_profile_v2():
            run = issued_runtime_run_v2(
                self.harness, runtime, browser, png,
            )
            self.evidence = build_spine42_v3_runtime_evidence_v2(run)
            self.bundle = build_spine42_v3_runtime_bundle_v2(self.evidence)

    @staticmethod
    def profile():
        return _fake_runtime_profile_v2()


def address(bundle):
    return (
        bundle.project_id, bundle.skeleton_json_sha256,
        bundle.spine42_v3_bundle_sha256, bundle.bundle_sha256,
    )


def publication_path(state_root, bundle):
    return (
        state_root / "builds" / bundle.project_id /
        "spine42-v3-runtime-v2" / bundle.skeleton_json_sha256 /
        bundle.spine42_v3_bundle_sha256 / bundle.bundle_sha256
    )


__all__ = ["RuntimeStorageV2Fixture", "address", "publication_path"]
