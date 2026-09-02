"""Deterministic official-execution fixture for P10.3c v2 tests."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from autospine_workbench.body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from autospine_workbench.body_sway_runtime_capture_session_v2 import (
    build_body_sway_runtime_capture_sessions_v2,
)
from autospine_workbench.body_sway_runtime_capture_v2_compiler import (
    compile_body_sway_runtime_capture_v2,
)
from autospine_workbench.body_sway_runtime_execution import (
    compile_body_sway_runtime_execution,
)
from autospine_workbench.body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecutionReader,
)
from autospine_workbench.body_sway_runtime_execution_store import (
    BodySwayRuntimeExecutionStore,
)
from autospine_workbench.body_sway_visual_review_address_v2 import (
    ExactVisualReviewAddressV2,
)
from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
)
from autospine_workbench.browser_version_identity import (
    browser_version_identity_sha256,
)
from autospine_workbench.temporary_body_sway_preview_v2 import (
    compile_temporary_body_sway_preview_v2,
)
from tests.body_sway_preview_v2_helpers import PreviewV2Fixture
from tests.body_sway_runtime_capture_helpers import (
    RUNTIME_CSS_SHA, RUNTIME_JS_SHA, capture_png, fake_runtime,
)
from tests.test_temporary_body_sway_preview_v2 import (
    _patched_source, _source_images,
)


@contextmanager
def fake_runtime_profile_v2():
    modules = (
        "autospine_workbench.body_sway_runtime_capture_session_v2",
        "autospine_workbench.body_sway_runtime_capture_session_v2_validation",
        "autospine_workbench.body_sway_runtime_capture_v2_fields",
    )
    patches = []
    for module in modules:
        patches.extend((
            patch(module + ".SPINE_PLAYER_JAVASCRIPT_SHA256", RUNTIME_JS_SHA),
            patch(module + ".SPINE_PLAYER_STYLESHEET_SHA256", RUNTIME_CSS_SHA),
        ))
    with patches[0], patches[1], patches[2], patches[3], \
            patches[4], patches[5]:
        yield


@dataclass(frozen=True)
class BodySwayVisualReviewV2Build:
    preview: object
    execution: object
    preview_inputs: object
    mesh_bundle: object


def build_visual_review_v2_bundle(root: Path):
    preview_fixture = PreviewV2Fixture(root / "preview")
    inputs = preview_fixture.admit()
    images = _source_images(preview_fixture.fixture.mesh.rig)
    with _patched_source(images):
        preview = compile_temporary_body_sway_preview_v2(
            inputs, preview_fixture.fixture.mesh,
        )
    runtime = replace(
        fake_runtime(root / "runtime"),
        package_json_sha256="a" * 64, license_sha256="b" * 64,
    )
    with fake_runtime_profile_v2():
        sessions = build_body_sway_runtime_capture_sessions_v2(preview, runtime)
        collector = BodySwayRuntimeCaptureCollector(sessions)
    for index, case_id in enumerate(collector.case_ids):
        collector.record_capture(
            case_id, capture_png(pixel=(20 + index, 40, 60, 255)),
            device_pixel_ratio=1,
        )
    snapshot = collector.snapshot()
    version = "128.0.6613.0"
    browser = BrowserExecutableSnapshot(
        path="C:\\fake\\chrome.exe", family="chromium",
        reported_version=version,
        version_output_sha256=browser_version_identity_sha256(
            "chromium", version,
        ),
        executable_sha256="c" * 64, size_bytes=4096,
    )
    with fake_runtime_profile_v2():
        capture = compile_body_sway_runtime_capture_v2(
            preview, runtime, sessions, snapshot, browser,
        )
        execution = compile_body_sway_runtime_execution(
            preview, runtime, sessions, snapshot, browser, capture,
            license_acknowledged=True,
        )
    return BodySwayVisualReviewV2Build(
        preview, execution, inputs, preview_fixture.fixture.mesh,
    )


def build_visual_review_v2_inputs(root: Path):
    bundle = build_visual_review_v2_bundle(root)
    return bundle.preview, bundle.execution


class BodySwayVisualReviewV2Fixture:
    def __init__(self, root: Path, preview, execution) -> None:
        self.state_root = root / "state"
        self.preview = preview
        self.execution = execution
        with fake_runtime_profile_v2():
            published = BodySwayRuntimeExecutionStore(self.state_root).publish(
                execution,
            )
            self.verified = VerifiedBodySwayRuntimeExecutionReader(
                self.state_root,
            ).load(
                published.project_id,
                published.temporary_preview_v2_sha256,
                published.bundle_sha256,
                published.artifact_set_sha256,
            )
        self.address = ExactVisualReviewAddressV2(
            published.project_id, published.temporary_preview_v2_sha256,
            published.bundle_sha256, published.artifact_set_sha256,
        )


def review_rows_v2(candidate, *, action="approve"):
    return [{
        "case_id": row["case_id"],
        "evidence_sha256": row["evidence_sha256"],
        "action": action,
        "notes": "" if action == "approve" else f"human {action}",
    } for row in candidate["cases"]]
