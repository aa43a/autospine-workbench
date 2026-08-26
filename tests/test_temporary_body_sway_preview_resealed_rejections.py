"""Resealed semantic counterexamples for TemporaryBodySwayPreview v1."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_preview_profile import (  # noqa: E402
    BASE_ANIMATION_NAME,
    CAPTURE_PLAN_DIGEST_DOMAIN,
    COMBINED_ANIMATION_NAME,
)
from autospine_workbench.motion_roles import (  # noqa: E402
    CANONICAL_BONE_ID_BY_ROLE,
)
from autospine_workbench.png_rgba import decode_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.temporary_body_sway_preview import (  # noqa: E402
    compile_temporary_body_sway_preview,
)
from autospine_workbench.temporary_body_sway_preview_inventory import (  # noqa: E402
    build_temporary_body_sway_preview_inventory,
    require_temporary_body_sway_preview_inventory,
)
from autospine_workbench.temporary_body_sway_preview_validation import (  # noqa: E402
    TemporaryBodySwayPreviewValidationError,
    require_temporary_body_sway_preview,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture  # noqa: E402


ROOT_BONE_ID = CANONICAL_BONE_ID_BY_ROLE["humanoid.root"]


def canonical_bytes(value) -> bytes:
    """Serialize a finite JSON value exactly like the production contracts."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def json_artifact(artifacts: dict[str, bytes], path: str) -> dict:
    """Return a detached JSON artifact for adversarial mutation."""

    value = json.loads(artifacts[path])
    if not isinstance(value, dict):
        raise AssertionError(f"Expected an object artifact: {path}")
    return value


def replace_json_artifact(
    artifacts: dict[str, bytes], path: str, value: dict
) -> None:
    artifacts[path] = canonical_bytes(value)


def reseal_capture_plan(plan: dict) -> None:
    """Recompute the public capture-plan seal after changing its cases."""

    body = deepcopy(plan)
    body.pop("capture_plan_sha256", None)
    plan["capture_plan_sha256"] = canonical_sha256({
        "domain": CAPTURE_PLAN_DIGEST_DOMAIN,
        **body,
    })


def reseal_package(document: dict, artifacts: dict[str, bytes]) -> None:
    """Refresh every outer byte seal so semantic validation is authoritative."""

    session = json_artifact(artifacts, "runtime/session.json")
    session["source"]["preview_projection_sha256"] = document[
        "projection"
    ]["projection_sha256"]
    session["capture_plan"] = deepcopy(document["capture_plan"])
    for role, path in (
        ("skeleton", "runtime/skeleton.json"),
        ("atlas", "runtime/skeleton.atlas"),
        ("texture", "runtime/skeleton.png"),
    ):
        session["assets"][role]["sha256"] = hashlib.sha256(
            artifacts[path]
        ).hexdigest()
    texture = decode_rgba_png(
        artifacts["runtime/skeleton.png"], source_name="skeleton.png"
    )
    session["assets"]["texture"]["size"] = [
        texture.width,
        texture.height,
    ]
    replace_json_artifact(artifacts, "runtime/session.json", session)

    document["artifacts"] = build_temporary_body_sway_preview_inventory(
        artifacts
    )
    require_temporary_body_sway_preview_inventory(document["artifacts"])
    document["summary"]["capture_case_count"] = len(
        document["capture_plan"]["cases"]
    )
    document["summary"]["artifact_file_count"] = len(artifacts)
    document["summary"]["artifact_total_bytes"] = sum(
        len(raw) for raw in artifacts.values()
    )


class TemporaryBodySwayPreviewResealedRejectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = BodySwayPreviewFixture(Path(cls.temporary.name))
        cls.value = compile_temporary_body_sway_preview(
            cls.fixture.preview_inputs, cls.fixture.chain.mesh_bundle
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def package(self) -> tuple[dict, dict[str, bytes]]:
        return deepcopy(self.value.document), self.value.artifact_bytes

    def assert_resealed_rejected(
        self, document: dict, artifacts: dict[str, bytes]
    ) -> None:
        reseal_package(document, artifacts)
        with self.assertRaises(TemporaryBodySwayPreviewValidationError):
            require_temporary_body_sway_preview(document, artifacts)

    def test_empty_combined_bones_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        skeleton = json_artifact(artifacts, "runtime/skeleton.json")
        skeleton["animations"][COMBINED_ANIMATION_NAME]["bones"] = {}
        replace_json_artifact(artifacts, "runtime/skeleton.json", skeleton)
        self.assert_resealed_rejected(document, artifacts)

    def test_out_of_bounds_atlas_region_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        lines = artifacts["runtime/skeleton.atlas"].decode("utf-8").splitlines()
        page_width = int(lines[1].removeprefix("size: ").split(",", 1)[0])
        lines[7] = f"  xy: {page_width}, 2"
        artifacts["runtime/skeleton.atlas"] = (
            "\n".join(lines) + "\n"
        ).encode("utf-8")
        self.assert_resealed_rejected(document, artifacts)

    def test_endpoint_only_capture_plan_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        duration = document["timing"]["duration_ticks"]
        document["capture_plan"]["cases"] = [
            row for row in document["capture_plan"]["cases"]
            if row["animation"] is None or row["tick"] in {0, duration}
        ]
        self.assertEqual(5, len(document["capture_plan"]["cases"]))
        reseal_capture_plan(document["capture_plan"])
        self.assert_resealed_rejected(document, artifacts)

    def test_attachment_path_mismatch_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        skeleton = json_artifact(artifacts, "runtime/skeleton.json")
        attachments = []
        for skin in skeleton["skins"]:
            for slot_attachments in skin["attachments"].values():
                attachments.extend(slot_attachments.items())
        self.assertGreaterEqual(len(attachments), 2)
        first_name, first = attachments[0]
        second_name, _second = attachments[1]
        self.assertNotEqual(first_name, second_name)
        first["path"] = second_name
        replace_json_artifact(artifacts, "runtime/skeleton.json", skeleton)
        self.assert_resealed_rejected(document, artifacts)

    def test_null_draw_order_offset_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        skeleton = json_artifact(artifacts, "runtime/skeleton.json")
        for animation_name in (BASE_ANIMATION_NAME, COMBINED_ANIMATION_NAME):
            skeleton["animations"][animation_name]["drawOrder"][0][
                "offsets"
            ] = [None]
        replace_json_artifact(artifacts, "runtime/skeleton.json", skeleton)
        self.assert_resealed_rejected(document, artifacts)

    def test_undeclared_event_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        skeleton = json_artifact(artifacts, "runtime/skeleton.json")
        declared = sorted(skeleton["events"])
        self.assertTrue(declared)
        skeleton["events"].pop(declared[0])
        replace_json_artifact(artifacts, "runtime/skeleton.json", skeleton)
        self.assert_resealed_rejected(document, artifacts)

    def test_nonempty_event_definition_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        skeleton = json_artifact(artifacts, "runtime/skeleton.json")
        event_name = next(iter(skeleton["events"]))
        skeleton["events"][event_name] = {"string": "forged"}
        replace_json_artifact(artifacts, "runtime/skeleton.json", skeleton)
        self.assert_resealed_rejected(document, artifacts)

    def test_extra_runtime_constraint_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        skeleton = json_artifact(artifacts, "runtime/skeleton.json")
        skeleton["ik"] = []
        replace_json_artifact(artifacts, "runtime/skeleton.json", skeleton)
        self.assert_resealed_rejected(document, artifacts)

    def test_changed_setup_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        skeleton = json_artifact(artifacts, "runtime/skeleton.json")
        skeleton["bones"][0]["x"] += 37
        replace_json_artifact(artifacts, "runtime/skeleton.json", skeleton)
        self.assert_resealed_rejected(document, artifacts)

    def test_non_root_translate_is_rejected_after_reseal(self) -> None:
        document, artifacts = self.package()
        skeleton = json_artifact(artifacts, "runtime/skeleton.json")
        base_bones = skeleton["animations"][BASE_ANIMATION_NAME]["bones"]
        destination = next(
            bone_id
            for bone_id in document["projection"]["rotation_bone_ids"]
            if bone_id != ROOT_BONE_ID and bone_id in base_bones
        )
        for animation_name in (BASE_ANIMATION_NAME, COMBINED_ANIMATION_NAME):
            bones = skeleton["animations"][animation_name]["bones"]
            translation = bones[ROOT_BONE_ID].pop("translate")
            if not bones[ROOT_BONE_ID]:
                bones.pop(ROOT_BONE_ID)
            bones[destination]["translate"] = translation
        replace_json_artifact(artifacts, "runtime/skeleton.json", skeleton)
        self.assert_resealed_rejected(document, artifacts)

    def test_top_level_project_or_clip_tamper_is_rejected_after_reseal(self) -> None:
        for field, changed in (
            ("project_id", "resealed-other-project"),
            ("clip_id", "resealed-other-clip"),
        ):
            with self.subTest(field=field):
                document, artifacts = self.package()
                document[field] = changed
                self.assert_resealed_rejected(document, artifacts)


if __name__ == "__main__":
    unittest.main()
