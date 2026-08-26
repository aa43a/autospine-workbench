"""One valid sealed runtime capture shared by command boundary tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile

from autospine_workbench.body_sway_runtime_capture import (
    compile_body_sway_runtime_capture,
)
from autospine_workbench.body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from autospine_workbench.body_sway_runtime_capture_store import (
    PublishedBodySwayRuntimeCapture,
)
from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
)
from autospine_workbench.p10_runtime_capture_runner import (
    P10RuntimeCaptureResult,
)
from tests.body_sway_runtime_capture_helpers import (
    RuntimeCaptureFixture,
    capture_png,
    fake_runtime_profile,
)


class RuntimeCaptureCommandFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        source = RuntimeCaptureFixture(root)
        browser = BrowserExecutableSnapshot(
            path=str(root / "chrome.exe"),
            family="chromium",
            reported_version="140.0.0.1",
            version_output_sha256=hashlib.sha256(
                b"Chromium 140.0.0.1\n"
            ).hexdigest(),
            executable_sha256="e" * 64,
            size_bytes=4096,
        )
        with fake_runtime_profile():
            collector = BodySwayRuntimeCaptureCollector(source.sessions)
            png = capture_png()
            for case_id in collector.case_ids:
                collector.record_capture(case_id, png, device_pixel_ratio=1)
            self.capture = compile_body_sway_runtime_capture(
                source.preview, source.runtime, source.sessions,
                collector.snapshot(), browser,
            )
        self.project_id = self.capture.document["project_id"]

    def close(self) -> None:
        self.temporary.cleanup()

    def runner_result(self, **changes) -> P10RuntimeCaptureResult:
        document = self.capture.document
        value = P10RuntimeCaptureResult(
            temporary_preview_sha256=(
                document["source"]["temporary_preview_sha256"]
            ),
            runtime_capture_sha256=self.capture.sha256,
            artifact_set_sha256=self.capture.artifact_set_sha256,
            browser_family=document["browser"]["family"],
            browser_reported_version=document["browser"]["reported_version"],
            case_count=len(document["cases"]),
            _capture=self.capture,
        )
        return replace(value, **changes)

    def publication(self, **changes) -> PublishedBodySwayRuntimeCapture:
        value = PublishedBodySwayRuntimeCapture(
            path=Path("state/published"),
            project_id=self.project_id,
            temporary_preview_sha256=(
                self.capture.document["source"]["temporary_preview_sha256"]
            ),
            manifest_sha256=self.capture.sha256,
            artifact_set_sha256=self.capture.artifact_set_sha256,
            bundle_sha256="d" * 64,
            reused=False,
        )
        return replace(value, **changes)
