"""Pure five-file P10.3 preview snapshot tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_preview_page import (  # noqa: E402
    body_sway_preview_player_html,
)
from autospine_workbench.body_sway_preview_session import (  # noqa: E402
    build_body_sway_preview_session,
)
from autospine_workbench.temporary_body_sway_preview_artifacts import (  # noqa: E402
    ARTIFACT_PATHS,
    TemporaryBodySwayPreviewArtifactError,
    compile_temporary_body_sway_preview_artifacts,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture  # noqa: E402
from tests.p9_v2_helpers import tree  # noqa: E402


class TemporaryBodySwayPreviewArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = BodySwayPreviewFixture(Path(cls.temporary.name))
        cls.before = tree(cls.fixture.persisted.state)
        cls.value = compile_temporary_body_sway_preview_artifacts(
            cls.fixture.preview_inputs, cls.fixture.chain.mesh_bundle
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_exact_five_files_are_deterministic_and_zero_write(self):
        second = compile_temporary_body_sway_preview_artifacts(
            self.fixture.preview_inputs, self.fixture.chain.mesh_bundle
        )
        self.assertEqual(self.value, second)
        self.assertEqual(self.before, tree(self.fixture.persisted.state))
        self.assertEqual(ARTIFACT_PATHS,
                         tuple(self.value.artifact_bytes))
        self.assertEqual(body_sway_preview_player_html(),
                         self.value.artifact_bytes["runtime/player.html"])

    def test_session_binds_runtime_assets_projection_and_capture_plan(self):
        files = self.value.artifact_bytes
        session = json.loads(files["runtime/session.json"])
        self.assertEqual(
            self.value.preview.projection.sha256,
            session["source"]["preview_projection_sha256"],
        )
        for role, path in (
            ("skeleton", "runtime/skeleton.json"),
            ("atlas", "runtime/skeleton.atlas"),
            ("texture", "runtime/skeleton.png"),
        ):
            self.assertEqual(hashlib.sha256(files[path]).hexdigest(),
                             session["assets"][role]["sha256"])
        self.assertEqual(self.value.capture_plan, session["capture_plan"])
        self.assertFalse(
            session["semantics"]["official_runtime_execution_claimed"]
        )

    def test_player_and_session_honor_non_loop_motion(self):
        raw = build_body_sway_preview_session(
            self.value.preview,
            self.value.atlas,
            self.value.capture_plan,
            loop=False,
        )
        self.assertFalse(json.loads(raw)["animations"]["loop"])
        page = body_sway_preview_player_html().decode("utf-8")
        self.assertIn("setAnimation(0, name, playbackLoop)", page)
        self.assertNotIn("setAnimation(0, name, true)", page)

    def test_values_are_frozen_and_accessors_are_copy_isolated(self):
        plan = self.value.capture_plan
        plan["cases"].clear()
        self.assertTrue(self.value.capture_plan["cases"])
        files = self.value.artifact_bytes
        files.clear()
        self.assertEqual(5, len(self.value.artifact_bytes))
        with self.assertRaises(FrozenInstanceError):
            self.value._artifact_items = ()  # type: ignore[misc]

    def test_p3_cross_wire_and_source_png_tamper_fail_closed(self):
        stale = replace(
            self.fixture.chain.mesh_bundle, bundle_sha256="f" * 64
        )
        with self.assertRaisesRegex(
            TemporaryBodySwayPreviewArtifactError, "P3 image bundle"
        ):
            compile_temporary_body_sway_preview_artifacts(
                self.fixture.preview_inputs, stale
            )
        path, raw = self.fixture.chain.mesh_bundle._source_png_items[0]
        tampered = replace(
            self.fixture.chain.mesh_bundle,
            _source_png_items=((path, raw + b"x"),)
            + self.fixture.chain.mesh_bundle._source_png_items[1:],
        )
        with self.assertRaises(TemporaryBodySwayPreviewArtifactError):
            compile_temporary_body_sway_preview_artifacts(
                self.fixture.preview_inputs, tampered
            )

    def test_never_calls_the_p6_release_bundle_contract(self):
        with patch(
            "autospine_workbench.spine42_bundle_contract."
            "build_spine42_bundle_contract"
        ) as release:
            compile_temporary_body_sway_preview_artifacts(
                self.fixture.preview_inputs, self.fixture.chain.mesh_bundle
            )
        release.assert_not_called()


if __name__ == "__main__":
    unittest.main()
