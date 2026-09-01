"""Pure completion checks and non-authoritative mount publication tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_capture_job_completion import (  # noqa: E402
    capture_result_matches, publish_visual_review_mount_best_effort,
)
from autospine_workbench.p10_runtime_capture_v2_commands import (  # noqa: E402
    P10RuntimeCaptureV2CommandResult,
)


SHA = {name: character * 64 for name, character in {
    "package": "1", "preview": "2", "execution": "3", "capture": "4",
    "preview_artifact": "5", "artifact": "6", "bundle": "7",
}.items()}
MODULE = "autospine_workbench.p10_capture_job_completion"


class P10CaptureJobCompletionTests(unittest.TestCase):
    def setUp(self):
        self.request = {"package_id": SHA["package"]}
        self.preview = SimpleNamespace(
            project_id="project", clip_id="idle",
            temporary_preview_v2_sha256=SHA["preview"], case_count=43,
        )
        self.result = P10RuntimeCaptureV2CommandResult(
            SHA["package"], "project", "idle", SHA["preview"],
            SHA["execution"], SHA["capture"], SHA["artifact"],
            SHA["bundle"], "google-chrome", "152.0.0.0", 43, False,
        )

    def test_capture_result_requires_every_exact_identity(self):
        self.assertTrue(capture_result_matches(
            self.request, self.preview, self.result,
        ))
        changes = {
            "package_id": SHA["preview"],
            "project_id": "other-project", "clip_id": "wave",
            "temporary_preview_v2_sha256": SHA["preview_artifact"],
            "case_count": 41,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                changed = replace(self.result, **{field: value})
                self.assertFalse(capture_result_matches(
                    self.request, self.preview, changed,
                ))
        with self.assertRaises(KeyError):
            capture_result_matches({}, self.preview, self.result)

    def test_mount_publication_saves_only_matching_record(self):
        projects = SimpleNamespace(state_root=Path("state"))
        record = SimpleNamespace(result=self.preview)
        cache = Mock()
        with patch(
            MODULE + ".compile_cached_body_sway_preview_v2_record",
            return_value=record,
        ) as compile_record, patch(
            MODULE + ".P10VisualReviewV2MountStore",
            return_value=cache,
        ) as store_type:
            publish_visual_review_mount_best_effort(
                projects, SHA["execution"], self.result,
            )
        compile_record.assert_called_once_with(projects, SHA["package"])
        store_type.assert_called_once_with(projects.state_root)
        cache.save.assert_called_once_with(SHA["execution"], record)

    def test_mount_publication_is_best_effort_and_rejects_crosswire(self):
        projects = SimpleNamespace(state_root=Path("state"))
        crosswired = SimpleNamespace(result=SimpleNamespace(
            project_id="other-project", clip_id="idle",
            temporary_preview_v2_sha256=SHA["preview"],
        ))
        with patch(
            MODULE + ".compile_cached_body_sway_preview_v2_record",
            return_value=crosswired,
        ), patch(MODULE + ".P10VisualReviewV2MountStore") as store_type:
            publish_visual_review_mount_best_effort(
                projects, SHA["execution"], self.result,
            )
        store_type.assert_not_called()
        with patch(
            MODULE + ".compile_cached_body_sway_preview_v2_record",
            side_effect=RuntimeError("cache unavailable"),
        ):
            publish_visual_review_mount_best_effort(
                projects, SHA["execution"], self.result,
            )


if __name__ == "__main__":
    unittest.main()
