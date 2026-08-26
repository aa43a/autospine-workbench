"""Exact published-capture fixtures for P10.3c visual review tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from autospine_workbench.body_sway_runtime_capture import (
    compile_body_sway_runtime_capture,
)
from autospine_workbench.body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from autospine_workbench.body_sway_runtime_capture_store import (
    BodySwayRuntimeCaptureStore,
)
from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
)
from tests.body_sway_runtime_capture_helpers import (
    RuntimeCaptureFixture,
    capture_png,
    fake_runtime_profile,
)


class BodySwayVisualReviewFixture:
    """Build and publish one complete deterministic runtime capture."""

    def __init__(self, root: Path) -> None:
        self.state_root = root / "state"
        input_root = root / "inputs"
        input_root.mkdir(parents=True)
        self.inputs = RuntimeCaptureFixture(input_root)
        with fake_runtime_profile():
            collector = BodySwayRuntimeCaptureCollector(self.inputs.sessions)
            image = capture_png()
            for case_id in collector.case_ids:
                collector.record_capture(case_id, image, device_pixel_ratio=1)
            browser = BrowserExecutableSnapshot(
                path=str(root / "chromium.exe"),
                family="chromium",
                reported_version="128.0.6613.0",
                version_output_sha256=hashlib.sha256(
                    b"Chromium 128.0.6613.0\n"
                ).hexdigest(),
                executable_sha256="b" * 64,
                size_bytes=4096,
            )
            self.capture = compile_body_sway_runtime_capture(
                self.inputs.preview,
                self.inputs.runtime,
                self.inputs.sessions,
                collector.snapshot(),
                browser,
            )
            self.published = BodySwayRuntimeCaptureStore(
                self.state_root
            ).publish(self.capture)

    @property
    def address(self) -> tuple[str, str, str, str]:
        """Return project, preview, bundle, and artifact-set identities."""

        value = self.published
        return (
            value.project_id,
            value.temporary_preview_sha256,
            value.bundle_sha256,
            value.artifact_set_sha256,
        )


def review_rows(candidate: dict, action: str = "approve") -> list[dict]:
    """Build one exhaustive, sorted human decision input."""

    return [
        {
            "case_id": row["case_id"],
            "evidence_sha256": row["evidence_sha256"],
            "action": action,
            "notes": "reviewed frame",
        }
        for row in candidate["cases"]
    ]
