"""Small deterministic fixture for detached RuntimeCapture v2 tests."""

from __future__ import annotations

from copy import deepcopy
import tempfile
from pathlib import Path

from autospine_workbench.body_sway_runtime_capture_v2 import (
    BodySwayRuntimeCaptureV2,
)
from autospine_workbench.body_sway_runtime_capture_v2_inventory import (
    build_body_sway_runtime_capture_v2_inventory,
)
from autospine_workbench.body_sway_runtime_capture_v2_profile import (
    RELEASE_GATE,
    SEMANTICS,
    body_sway_runtime_capture_v2_compiler_profile,
)
from autospine_workbench.body_sway_runtime_capture_v2_validation import (
    body_sway_runtime_capture_v2_case_stream_sha256,
)
from autospine_workbench.browser_version_identity import (
    browser_version_identity_sha256,
)
from autospine_workbench.spine42_contract import (
    SPINE_RUNTIME_PACKAGE,
    SPINE_RUNTIME_VERSION,
)
from autospine_workbench.spine42_runtime_contract import RUNTIME_NPM_INTEGRITY
from autospine_workbench.spine42_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture
from tests.body_sway_runtime_capture_helpers import capture_png


class RuntimeCaptureV2Fixture:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.preview_fixture = BodySwayPreviewFixture(root)
        inputs = self.preview_fixture.preview_inputs
        self.plan_cases = [
            {"case_id": "setup", "animation": None,
             "tick": 0, "time_seconds": 0.0},
            {"case_id": "base-t000000000", "animation": "p10.base",
             "tick": 0, "time_seconds": 0.0},
            {"case_id": "combined-t000000000", "animation": "p10.body-sway",
             "tick": 0, "time_seconds": 0.0},
        ]
        self.capture_bytes = {
            f"captures/{row['case_id']}.png": capture_png()
            for row in self.plan_cases
        }
        inventory = build_body_sway_runtime_capture_v2_inventory(
            [row["case_id"] for row in self.plan_cases], self.capture_bytes,
        )
        captured = [
            {
                **row,
                "image_path": inventory["files"][index]["path"],
                "png_sha256": inventory["files"][index]["sha256"],
            }
            for index, row in enumerate(self.plan_cases)
        ]
        viewport = {"x": -64.25, "y": -88.5,
                    "width": 1152.0, "height": 1152.0}
        plan_sha = "4" * 64
        version = "128.0.6613.0"
        self.document = {
            "format": "autospine-body-sway-runtime-capture",
            "format_version": 2,
            "project_id": inputs.project_id,
            "clip_id": inputs.clip_id,
            "source": {
                "temporary_preview_v2_sha256": "1" * 64,
                "preview_artifact_set_sha256": "2" * 64,
                "preview_projection_v2_sha256": "3" * 64,
                "capture_plan_v2_sha256": plan_sha,
                "preview_source_sha256": "6" * 64,
                "capture_framing_candidate_sha256": "7" * 64,
                "capture_framing_decision_sha256": "8" * 64,
                "capture_framing_revision": 2,
                "body_sway_probe_report_sha256": "9" * 64,
                "current_p10_1_head": {
                    "candidate_sha256": "a" * 64,
                    "decision_sha256": "b" * 64,
                    "revision": 3,
                },
                "world_viewport": dict(viewport),
            },
            "timing": inputs.timing,
            "selection": inputs.selection,
            "compiler": body_sway_runtime_capture_v2_compiler_profile(),
            "semantics": deepcopy(SEMANTICS),
            "runtime": {
                "package": SPINE_RUNTIME_PACKAGE,
                "version": SPINE_RUNTIME_VERSION,
                "npm_integrity": RUNTIME_NPM_INTEGRITY,
                "javascript_sha256": SPINE_PLAYER_JAVASCRIPT_SHA256,
                "stylesheet_sha256": SPINE_PLAYER_STYLESHEET_SHA256,
            },
            "assets": {
                "skeleton_sha256": "c" * 64,
                "atlas_sha256": "d" * 64,
                "texture_sha256": "e" * 64,
                "texture_size": [1024, 1024],
            },
            "browser": {
                "family": "chromium", "reported_version": version,
                "version_output_sha256":
                    browser_version_identity_sha256("chromium", version),
                "executable_sha256": "f" * 64,
                "executable_size": 4096,
                "identity_scope": "launcher-executable-and-reported-version",
            },
            "capture": {
                "viewport": {"width": 640, "height": 640},
                "device_pixel_ratio": 1,
                "background": "#20242aff",
                "preserve_drawing_buffer": True,
                "world_viewport": dict(viewport),
                "capture_plan_sha256": plan_sha,
                "case_stream_sha256":
                    body_sway_runtime_capture_v2_case_stream_sha256(captured),
                "cases": self.plan_cases,
            },
            "cases": captured,
            "artifacts": inventory,
            "status":
                "validated_capture_payload_ready_for_official_runtime_execution",
            "release_gate": deepcopy(RELEASE_GATE),
            "summary": {
                "case_count": 3, "setup_case_count": 1,
                "base_case_count": 1, "combined_case_count": 1,
                "runtime_error_count": 0,
                "png_total_bytes": inventory["total_bytes"],
            },
        }
        self.capture = BodySwayRuntimeCaptureV2.from_detached(
            self.document, self.capture_bytes
        )


def build_runtime_capture_v2_fixture():
    temporary = tempfile.TemporaryDirectory()
    return temporary, RuntimeCaptureV2Fixture(Path(temporary.name))


def capture_v2_for_preview(preview, template: RuntimeCaptureV2Fixture):
    """Create detached capture bytes exactly bound to one real Preview v2."""

    document = deepcopy(template.document)
    source = preview.document["source"]
    projection = preview.document["projection"]
    plan = preview.document["capture_plan"]
    document.update({
        "project_id": preview.document["project_id"],
        "clip_id": preview.document["clip_id"],
        "timing": preview.document["timing"],
        "selection": preview.document["selection"],
    })
    document["source"].update({
        "temporary_preview_v2_sha256": preview.sha256,
        "preview_artifact_set_sha256": preview.artifact_set_sha256,
        "preview_projection_v2_sha256": projection["projection_sha256"],
        "capture_plan_v2_sha256": plan["capture_plan_sha256"],
        "preview_source_sha256": _canonical_sha256(source),
        "capture_framing_candidate_sha256":
            source["capture_framing_candidate_sha256"],
        "capture_framing_decision_sha256":
            source["capture_framing_decision_sha256"],
        "capture_framing_revision": source["capture_framing_revision"],
        "body_sway_probe_report_sha256":
            source["body_sway_probe_report_sha256"],
        "current_p10_1_head": source["current_p10_1_head"],
        "world_viewport": plan["world_viewport"],
    })
    paths = [row["case_id"] for row in plan["cases"]]
    image = capture_png()
    captures = {f"captures/{case_id}.png": image for case_id in paths}
    inventory = build_body_sway_runtime_capture_v2_inventory(paths, captures)
    cases = [
        {
            **row,
            "image_path": inventory["files"][index]["path"],
            "png_sha256": inventory["files"][index]["sha256"],
        }
        for index, row in enumerate(plan["cases"])
    ]
    document["capture"].update({
        "viewport": plan["viewport"],
        "device_pixel_ratio": plan["device_pixel_ratio"],
        "background": plan["background"],
        "preserve_drawing_buffer": plan["preserve_drawing_buffer"],
        "world_viewport": plan["world_viewport"],
        "capture_plan_sha256": plan["capture_plan_sha256"],
        "case_stream_sha256":
            body_sway_runtime_capture_v2_case_stream_sha256(cases),
        "cases": plan["cases"],
    })
    document["cases"] = cases
    document["artifacts"] = inventory
    roles = {row["role"]: row for row in preview.document["artifacts"]["files"]}
    document["assets"] = {
        "skeleton_sha256": roles["spine-skeleton-v2"]["sha256"],
        "atlas_sha256": roles["spine-atlas"]["sha256"],
        "texture_sha256": roles["spine-texture"]["sha256"],
        "texture_size": [
            preview.document["summary"]["atlas_width"],
            preview.document["summary"]["atlas_height"],
        ],
    }
    pair_count = (len(cases) - 1) // 2
    document["summary"] = {
        "case_count": len(cases), "setup_case_count": 1,
        "base_case_count": pair_count, "combined_case_count": pair_count,
        "runtime_error_count": 0,
        "png_total_bytes": inventory["total_bytes"],
    }
    return BodySwayRuntimeCaptureV2.from_detached(document, captures)


def _canonical_sha256(value):
    from autospine_workbench.resolved_project import canonical_sha256
    return canonical_sha256(value)
