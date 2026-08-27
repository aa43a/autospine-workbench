"""Persistence, projection, and materialization integration for split decisions."""

from __future__ import annotations

from copy import deepcopy
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

from autospine_workbench.artifact_store import ImmutableJsonArtifactStore  # noqa: E402
from autospine_workbench.contracts import (  # noqa: E402
    ContractValidationError,
)
from autospine_workbench.layer_manifest import (  # noqa: E402
    LayerManifestBuilder,
    LayerManifestBundleStore,
)
from autospine_workbench.layer_split_materializer import (  # noqa: E402
    LayerSplitMaterializationError,
    materialize_bilateral_splits,
)
from autospine_workbench.override_store import (  # noqa: E402
    OverrideHistoryStore,
    OverrideStateError,
)
from autospine_workbench.png_rgba import RgbaImage, write_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import ResolvedProjectBuilder  # noqa: E402
from autospine_workbench.region_rig_contract import review_gate  # noqa: E402
from autospine_workbench.split_preview import build_split_preview  # noqa: E402
from tests.test_layer_split_materializer import (  # noqa: E402
    LAYER_ID,
    project_fixture,
    source_image,
)


def proxy(identity: str, xy: list[int]) -> dict:
    return {
        "kind": "manual_proxy",
        "proxy_id": identity,
        "xy": xy,
        "label": "visible garment guide",
        "reason": "fixture pins visible artwork instead of hidden anatomy",
    }


def split_spec() -> dict:
    return {
        "parts": {
            side: {
                "guide": [
                    proxy(f"guide-upper.{side}", [x, 0]),
                    proxy(f"guide-lower.{side}", [x, 3]),
                ],
                "pivot": proxy(f"pivot.{side}", [x, 2]),
                "candidate_bone": f"thigh.{side}",
            }
            for side, x in (("left", 2), ("right", 5))
        }
    }


class SplitPersistenceFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.state = root / "state"
        self.source = root / "source.png"
        write_rgba_png(self.source, source_image())
        raw = project_fixture()
        layer = deepcopy(raw["resolved"]["layers"][0])
        for field in ("review_state", "reviewed_fields", "decision_revision"):
            layer.pop(field, None)
        layer.pop("candidate_bone", None)
        skeleton = deepcopy(raw["resolved"]["skeleton"])
        for joint in skeleton["joints"]:
            joint["confidence"] = 1.0
            for field in (
                "review_state",
                "decision_kind",
                "decision_revision",
                "decision",
                "review_reason",
                "legacy_review_confidence",
            ):
                joint.pop(field, None)
        skeleton["generation"] = {"method": "fixture", "requires_review": False}
        self.base = {
            "id": raw["id"],
            "source": deepcopy(raw["source"]),
            "canvas": deepcopy(raw["canvas"]),
            "layers": [layer],
            "skeleton": skeleton,
        }
        self.base["canvas"]["coordinate_system"] = "canvas-top-left-y-down"
        self.store = OverrideHistoryStore(self.state)
        initial = {
            "schema_version": "autospine-workbench.override/v3",
            "base_revision": 0,
            "joint_overrides": {},
            "joint_decisions": {},
            "layer_overrides": self._split_authoring(),
            "split_decisions": {},
            "notes": "split authoring",
        }
        self.empty = self.store.save(
            self.base["id"], initial, **self.context
        )
        self.initial_revision = self.empty["revision"]
        project = deepcopy(self.base)
        project["overrides"] = deepcopy(self.empty)
        project["resolved"] = ResolvedProjectBuilder().build(self.base, self.empty)
        materialized = materialize_bilateral_splits(
            project, {LAYER_ID: self.source}, root / "preview-layers"
        )
        manifest = LayerManifestBuilder().build(
            project,
            materialized.assets,
            materialized_layers=materialized.layers,
        )
        _bundle, manifest_sha = LayerManifestBundleStore(self.state).publish(
            self.base["id"], manifest, materialized.assets
        )
        preview = build_split_preview(
            project,
            materialized,
            manifest,
            layer_manifest_sha256=manifest_sha,
            parent_layer_id=LAYER_ID,
        )
        self.artifact = ImmutableJsonArtifactStore(self.state).publish(
            "split-previews", self.base["id"], preview
        )

    @property
    def context(self) -> dict:
        return {
            "joint_ids": {joint["id"] for joint in self.base["skeleton"]["joints"]},
            "layer_ids": {LAYER_ID},
            "canvas_width": self.base["canvas"]["width"],
            "canvas_height": self.base["canvas"]["height"],
            "base_project": self.base,
            "source_paths": {LAYER_ID: self.source},
        }

    def decision(self, action: str = "accept") -> dict:
        value = {
            "action": action,
            "split_artifact_sha256": self.artifact.sha256,
        }
        if action == "reject":
            value["reason"] = "visible garment partition needs another pass"
        return value

    @staticmethod
    def _split_authoring() -> dict:
        return {
            LAYER_ID: {
                "side": "bilateral",
                "disposition": "split_left_right",
                "split_spec": split_spec(),
            }
        }

    def payload(
        self,
        revision: int,
        *,
        decision: dict | None = None,
        layer_overrides: dict | None = None,
        notes: str = "split review",
    ) -> dict:
        return {
            "schema_version": "autospine-workbench.override/v3",
            "base_revision": revision + self.initial_revision,
            "joint_overrides": {},
            "joint_decisions": {},
            "layer_overrides": (
                deepcopy(layer_overrides)
                if layer_overrides is not None
                else self._split_authoring()
            ),
            "split_decisions": ({LAYER_ID: decision} if decision is not None else {}),
            "notes": notes,
        }


class SplitDecisionPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fx = SplitPersistenceFixture(Path(self.temp.name))

    def test_save_history_reload_and_action_changes_reuse_derived_fields(self) -> None:
        first = self.fx.store.save(
            self.fx.base["id"],
            self.fx.payload(0, decision=self.fx.decision()),
            **self.fx.context,
        )
        self.assertEqual("current", first["split_decisions"][LAYER_ID]["binding_status"])
        second = self.fx.store.save(
            self.fx.base["id"],
            self.fx.payload(1, decision=self.fx.decision("reject")),
            **self.fx.context,
        )
        current = second["split_decisions"][LAYER_ID]
        self.assertEqual("reject", current["action"])
        self.assertEqual(
            first["split_decisions"][LAYER_ID]["analysis"], current["analysis"]
        )
        third = self.fx.store.save(
            self.fx.base["id"],
            self.fx.payload(2, decision=self.fx.decision("reject"), notes="unrelated"),
            **self.fx.context,
        )
        reloaded = OverrideHistoryStore(self.fx.state).load(
            self.fx.base["id"], **self.fx.context
        )
        self.assertEqual(third, reloaded)
        history = self.fx.state / "overrides" / self.fx.base["id"] / "history"
        self.assertEqual(
            [
                "r000001.json",
                "r000002.json",
                "r000003.json",
                "r000004.json",
            ],
            sorted(path.name for path in history.glob("*.json")),
        )

    def test_full_document_save_can_remove_a_split_decision(self) -> None:
        self.fx.store.save(
            self.fx.base["id"], self.fx.payload(0, decision=self.fx.decision()), **self.fx.context
        )
        removed = self.fx.store.save(
            self.fx.base["id"], self.fx.payload(1, decision=None), **self.fx.context
        )
        self.assertEqual({}, removed["split_decisions"])
        self.assertEqual(
            {},
            self.fx.store.load(self.fx.base["id"], **self.fx.context)["split_decisions"],
        )

    def test_unchanged_decision_may_become_stale_with_authoring_change(self) -> None:
        saved = self.fx.store.save(
            self.fx.base["id"], self.fx.payload(0, decision=self.fx.decision()), **self.fx.context
        )
        authored = split_spec()
        authored["parts"]["left"]["pivot"]["xy"] = [3, 2]
        patch = {
            LAYER_ID: {
                "side": "bilateral",
                "disposition": "split_left_right",
                "split_spec": authored,
            }
        }
        client = {
            key: saved["split_decisions"][LAYER_ID][key]
            for key in ("action", "split_artifact_sha256")
        }
        stale = self.fx.store.save(
            self.fx.base["id"],
            self.fx.payload(1, decision=client, layer_overrides=patch),
            **self.fx.context,
        )
        self.assertEqual("stale", stale["split_decisions"][LAYER_ID]["binding_status"])
        resolved = ResolvedProjectBuilder().build(self.fx.base, stale)
        self.assertEqual([LAYER_ID], resolved["qa"]["stale_split_layer_ids"])
        self.assertEqual([], resolved["qa"]["accepted_split_layer_ids"])
        self.assertEqual("needs_review", resolved["qa"]["status"])

    def test_new_or_changed_decision_cannot_be_stale_prospectively(self) -> None:
        authored = split_spec()
        authored["parts"]["left"]["pivot"]["xy"] = [3, 2]
        patch = {
            LAYER_ID: {
                "side": "bilateral",
                "disposition": "split",
                "split_spec": authored,
            }
        }
        with self.assertRaises(ContractValidationError):
            self.fx.store.save(
                self.fx.base["id"],
                self.fx.payload(0, decision=self.fx.decision(), layer_overrides=patch),
                **self.fx.context,
            )
        self.assertEqual(
            self.fx.initial_revision,
            self.fx.store.load(self.fx.base["id"], **self.fx.context)["revision"],
        )

        saved = self.fx.store.save(
            self.fx.base["id"], self.fx.payload(0, decision=self.fx.decision()), **self.fx.context
        )
        with self.assertRaises(ContractValidationError):
            self.fx.store.save(
                self.fx.base["id"],
                self.fx.payload(1, decision=self.fx.decision("reject"), layer_overrides=patch),
                **self.fx.context,
            )
        self.assertEqual(saved, self.fx.store.load(self.fx.base["id"], **self.fx.context))

    def test_source_change_marks_stored_stale_and_rejects_new_decision(self) -> None:
        saved = self.fx.store.save(
            self.fx.base["id"], self.fx.payload(0, decision=self.fx.decision()), **self.fx.context
        )
        changed = source_image()
        pixels = bytearray(changed.pixels)
        pixels[4] ^= 1
        write_rgba_png(
            self.fx.source, RgbaImage(changed.width, changed.height, bytes(pixels))
        )
        loaded = self.fx.store.load(self.fx.base["id"], **self.fx.context)
        self.assertEqual("stale", loaded["split_decisions"][LAYER_ID]["binding_status"])

        other = SplitPersistenceFixture(Path(self.temp.name) / "new")
        image = source_image()
        modified = bytearray(image.pixels)
        modified[4] ^= 1
        write_rgba_png(other.source, RgbaImage(image.width, image.height, bytes(modified)))
        with self.assertRaises(ContractValidationError):
            other.store.save(
                other.base["id"], other.payload(0, decision=other.decision()), **other.context
            )
        self.assertEqual(self.fx.initial_revision + 1, saved["revision"])

    def test_algorithm_upgrade_marks_stored_decision_stale(self) -> None:
        self.fx.store.save(
            self.fx.base["id"], self.fx.payload(0, decision=self.fx.decision()), **self.fx.context
        )
        with patch(
            "autospine_workbench.split_binding_target.SPLIT_ALGORITHM_VERSION",
            "2.0.0",
        ):
            loaded = self.fx.store.load(self.fx.base["id"], **self.fx.context)
        self.assertEqual("stale", loaded["split_decisions"][LAYER_ID]["binding_status"])

    def test_persisted_derived_tamper_is_a_hard_load_error(self) -> None:
        self.fx.store.save(
            self.fx.base["id"], self.fx.payload(0, decision=self.fx.decision()), **self.fx.context
        )
        latest = self.fx.state / "overrides" / self.fx.base["id"] / "latest.json"
        document = json.loads(latest.read_text(encoding="utf-8"))
        document["split_decisions"][LAYER_ID]["review_target_sha256"] = "f" * 64
        latest.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(OverrideStateError):
            self.fx.store.load(self.fx.base["id"], **self.fx.context)

    def test_materializer_and_manifest_distinguish_current_accept_from_stale(self) -> None:
        accepted = self.fx.store.save(
            self.fx.base["id"], self.fx.payload(0, decision=self.fx.decision()), **self.fx.context
        )
        current_project = deepcopy(self.fx.base)
        current_project["overrides"] = deepcopy(accepted)
        current_project["resolved"] = ResolvedProjectBuilder().build(self.fx.base, accepted)
        current = materialize_bilateral_splits(
            current_project,
            {LAYER_ID: self.fx.source},
            self.fx.root / "accepted-layers",
        )
        manifest = LayerManifestBuilder().build(
            current_project, current.assets, materialized_layers=current.layers
        )
        children = [layer for layer in manifest["layers"] if "--" in layer["layer_id"]]
        self.assertTrue(all(child["qa"]["status"] == "passed" for child in children))
        self.assertTrue(all(child["semantic"]["mapping_method"] == "manual" for child in children))
        self.assertFalse(review_gate(manifest, current_project["resolved"], False))
        overlay_children = [layer for layer in current.layers if "--" in layer["id"]]
        for child in overlay_children:
            self.assertEqual(
                ["canonical_role", "side", "disposition", "pivot_xy", "candidate_bone"],
                child["reviewed_fields"],
            )
            self.assertEqual(f"thigh.{child['side']}", child["candidate_bone"])
            self.assertNotIn("proposed_candidate_bone", child)

        stale = deepcopy(accepted)
        stale["split_decisions"][LAYER_ID]["binding_status"] = "stale"
        stale_project = deepcopy(self.fx.base)
        stale_project["overrides"] = deepcopy(stale)
        stale_project["resolved"] = ResolvedProjectBuilder().build(self.fx.base, stale)
        materialized = materialize_bilateral_splits(
            stale_project,
            {LAYER_ID: self.fx.source},
            self.fx.root / "stale-layers",
        )
        stale_manifest = LayerManifestBuilder().build(
            stale_project, materialized.assets, materialized_layers=materialized.layers
        )
        stale_children = [
            layer for layer in stale_manifest["layers"] if "--" in layer["layer_id"]
        ]
        for child in stale_children:
            self.assertEqual("manual_required", child["qa"]["status"])
            self.assertTrue(
                {
                    "SEMANTIC_REVIEW_REQUIRED",
                    "PIVOT_REVIEW_REQUIRED",
                    "BONE_BINDING_REVIEW_REQUIRED",
                }.issubset(child["qa"]["flags"])
            )

        for field in ("operation_config_sha256", "split_spec_sha256"):
            with self.subTest(field=field):
                invalid = deepcopy(accepted)
                decision = invalid["split_decisions"][LAYER_ID]
                if field == "split_spec_sha256":
                    decision["analysis"][field] = "f" * 64
                else:
                    decision[field] = "f" * 64
                invalid_project = deepcopy(self.fx.base)
                invalid_project["resolved"] = ResolvedProjectBuilder().build(
                    self.fx.base, invalid
                )
                with self.assertRaises(LayerSplitMaterializationError):
                    materialize_bilateral_splits(
                        invalid_project,
                        {LAYER_ID: self.fx.source},
                        self.fx.root / f"invalid-{field}",
                    )


if __name__ == "__main__":
    unittest.main()
