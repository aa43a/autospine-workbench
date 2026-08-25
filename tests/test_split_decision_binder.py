"""Evidence binding and stale/current classification for split decisions."""

from __future__ import annotations

from copy import deepcopy
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
from autospine_workbench.alpha_bilateral_split import (  # noqa: E402
    AlphaBilateralSplitError,
)
from autospine_workbench.layer_manifest import (  # noqa: E402
    LayerManifestBuilder,
    LayerManifestBundleStore,
)
from autospine_workbench.layer_split_materializer import (  # noqa: E402
    materialize_bilateral_splits,
)
from autospine_workbench.png_rgba import RgbaImage, write_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.split_decision_binder import (  # noqa: E402
    SplitDecisionBinder,
    SplitDecisionBindingError,
)
from autospine_workbench.split_preview import build_split_preview  # noqa: E402
from tests.test_layer_split_materializer import (  # noqa: E402
    LAYER_ID,
    authored_split_spec,
    project_fixture,
    source_image,
)


def _rehash(resolved: dict) -> None:
    resolved.pop("sha256", None)
    resolved["sha256"] = canonical_sha256(resolved)


class SplitDecisionBinderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.source = self.root / "source.png"
        write_rgba_png(self.source, source_image())
        self.project = project_fixture()
        resolved = self.project["resolved"]
        resolved.update(
            schema_version="autospine.resolved-project/v1",
            project_id=self.project["id"],
            inputs={"base_project_sha256": "d" * 64, "override_sha256": "e" * 64},
        )
        spec = authored_split_spec()
        spec["parts"]["left"]["candidate_bone"] = "thigh.left"
        spec["parts"]["right"]["candidate_bone"] = "thigh.right"
        resolved["layers"][0]["split_spec"] = spec
        resolved["skeleton"]["bones"] = [
            {"id": "thigh.left"},
            {"id": "thigh.right"},
        ]
        _rehash(resolved)
        materialized = materialize_bilateral_splits(
            self.project, {LAYER_ID: self.source}, self.root / "derived"
        )
        self.assets = materialized.assets
        manifest = LayerManifestBuilder().build(
            self.project,
            materialized.assets,
            materialized_layers=materialized.layers,
        )
        self.preview_manifest = manifest
        _bundle, manifest_sha = LayerManifestBundleStore(self.state).publish(
            self.project["id"], manifest, materialized.assets
        )
        self.preview = build_split_preview(
            self.project,
            materialized,
            manifest,
            layer_manifest_sha256=manifest_sha,
            parent_layer_id=LAYER_ID,
        )
        self.published = ImmutableJsonArtifactStore(self.state).publish(
            "split-previews", self.project["id"], self.preview
        )
        self.binder = SplitDecisionBinder(self.state)
        self.sources = {LAYER_ID: self.source}

    def decision(self, *, action: str = "accept", digest: str | None = None) -> dict:
        item = {
            "action": action,
            "split_artifact_sha256": digest or self.published.sha256,
        }
        if action == "reject":
            item["reason"] = "partition does not follow the visible garment"
        return {LAYER_ID: item}

    def bind(self, decisions: dict, *, resolved: dict | None = None, stored=False):
        return self.binder.bind(
            self.project["id"],
            decisions,
            resolved=resolved or self.project["resolved"],
            source_paths=self.sources,
            stored=stored,
        )

    def assert_error(
        self, code: str, decisions: dict, *, resolved: dict | None = None, stored=False
    ) -> SplitDecisionBindingError:
        with self.assertRaises(SplitDecisionBindingError) as caught:
            self.bind(decisions, resolved=resolved, stored=stored)
        self.assertEqual(code, caught.exception.issues[0].code)
        self.assertEqual(code, caught.exception.as_validation_issues()[0].code)
        return caught.exception

    def test_accept_and_reject_derive_exact_current_provenance(self) -> None:
        for action in ("accept", "reject"):
            with self.subTest(action=action):
                bound = self.bind(self.decision(action=action))[LAYER_ID]
                self.assertEqual("current", bound["binding_status"])
                self.assertEqual(
                    self.preview["operation_config_sha256"],
                    bound["operation_config_sha256"],
                )
                self.assertEqual(
                    self.preview["review_target_sha256"],
                    bound["review_target_sha256"],
                )
                self.assertEqual(
                    canonical_sha256(self.preview["split_spec"]),
                    bound["analysis"]["split_spec_sha256"],
                )
                self.assertEqual(
                    self.preview["review_target"]["operation"]["algorithm"]["version"],
                    bound["analysis"]["algorithm_version"],
                )
                self.assertEqual(bound, self.bind({LAYER_ID: bound}, stored=True)[LAYER_ID])

    def test_client_cannot_spoof_any_derived_field(self) -> None:
        stored = self.bind(self.decision())[LAYER_ID]
        for field in (
            "operation_config_sha256",
            "review_target_sha256",
            "analysis",
            "binding_status",
        ):
            with self.subTest(field=field):
                decision = self.decision()[LAYER_ID]
                decision[field] = deepcopy(stored[field])
                self.assert_error("derived_field", {LAYER_ID: decision})

    def test_stored_artifact_fields_must_match_but_status_is_recomputed(self) -> None:
        stored = self.bind(self.decision())
        for field in ("operation_config_sha256", "review_target_sha256", "analysis"):
            with self.subTest(field=field):
                changed = deepcopy(stored)
                if field == "analysis":
                    changed[LAYER_ID][field]["algorithm_id"] = "substituted"
                else:
                    changed[LAYER_ID][field] = "f" * 64
                self.assert_error("derived_mismatch", changed, stored=True)

        stale_resolved = deepcopy(self.project["resolved"])
        stale_resolved["layers"][0]["canonical_role"] = "body.leg.lower"
        _rehash(stale_resolved)
        stored[LAYER_ID]["binding_status"] = "current"
        rebound = self.bind(stored, resolved=stale_resolved, stored=True)
        self.assertEqual("stale", rebound[LAYER_ID]["binding_status"])

    def test_client_requires_preview_snapshot_but_stored_revalidates_target(self) -> None:
        stored = self.bind(self.decision())
        newer = deepcopy(self.project["resolved"])
        newer["revision"] += 1
        _rehash(newer)
        self.assert_error("stale_artifact", self.decision(), resolved=newer)
        rebound = self.bind(stored, resolved=newer, stored=True)
        self.assertEqual("current", rebound[LAYER_ID]["binding_status"])

    def test_current_split_spec_guide_pivot_bone_role_and_draw_order_are_bound(self) -> None:
        mutations = {
            "guide": lambda value: value["skeleton"]["joints"][0].update(x=2.5),
            "pivot": lambda value: value["layers"][0]["split_spec"]["parts"]["left"][
                "pivot"
            ].update(xy=[2.5, 3.0]),
            "bone": lambda value: value["skeleton"]["bones"].pop(),
            "role": lambda value: value["layers"][0].update(canonical_role="body.leg.lower"),
            "draw order": lambda value: value["layers"].append(
                {"id": "layer-before", "z_index": -1, "disposition": "keep"}
            ),
        }
        stored = self.bind(self.decision())
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = deepcopy(self.project["resolved"])
                mutate(changed)
                _rehash(changed)
                self.assertEqual(
                    "stale",
                    self.bind(stored, resolved=changed, stored=True)[LAYER_ID][
                        "binding_status"
                    ],
                )
                self.assert_error("stale_artifact", self.decision(), resolved=changed)

    def test_current_source_png_and_rgba_identity_are_bound(self) -> None:
        stored = self.bind(self.decision())
        original = self.source.read_bytes()
        image = source_image()
        pixels = bytearray(image.pixels)
        pixels[0] ^= 1
        write_rgba_png(self.source, RgbaImage(image.width, image.height, bytes(pixels)))
        try:
            rebound = self.bind(stored, stored=True)
            self.assertEqual("stale", rebound[LAYER_ID]["binding_status"])
            self.assert_error("stale_artifact", self.decision())
        finally:
            self.source.write_bytes(original)

    def test_artifact_manifest_cross_mismatch_is_a_hard_error(self) -> None:
        changed = deepcopy(self.preview)
        changed["review_target"]["operation"]["algorithm"]["version"] = "999.0"
        changed["review_target_sha256"] = canonical_sha256(changed["review_target"])
        published = ImmutableJsonArtifactStore(self.state).publish(
            "split-previews", self.project["id"], changed
        )
        client = self.decision(digest=published.sha256)
        self.assert_error("artifact_invalid", client)
        stored = self._stored_for(changed, published.sha256)
        self.assert_error("artifact_invalid", stored, stored=True)

    def test_matching_historical_algorithm_is_stale_not_invalid(self) -> None:
        manifest = deepcopy(self.preview_manifest)
        operation_sha = None
        for child in manifest["layers"][1:3]:
            config = child["derivation"]["operation_config"]
            config["algorithm"]["version"] = "0.9.0"
            operation_sha = canonical_sha256(config)
            child["derivation"]["operation_config_sha256"] = operation_sha
        _path, manifest_sha = LayerManifestBundleStore(self.state).publish(
            self.project["id"], manifest, self.assets
        )
        preview = deepcopy(self.preview)
        preview["layer_manifest_sha256"] = manifest_sha
        operation = preview["review_target"]["operation"]
        operation["algorithm"]["version"] = "0.9.0"
        operation["config_sha256"] = operation_sha
        preview["operation_config_sha256"] = operation_sha
        preview["review_target_sha256"] = canonical_sha256(preview["review_target"])
        artifact = ImmutableJsonArtifactStore(self.state).publish(
            "split-previews", self.project["id"], preview
        )
        client = self.decision(digest=artifact.sha256)
        self.assert_error("stale_artifact", client)
        stored = self._stored_for(preview, artifact.sha256)
        rebound = self.bind(stored, stored=True)
        self.assertEqual("stale", rebound[LAYER_ID]["binding_status"])

    def test_manifest_children_must_remain_unreviewed_targets(self) -> None:
        mutations = {
            "semantic": lambda child: child["semantic"].update(mapping_method="manual"),
            "pivot": lambda child: child["rig_hint"]["pivot"].update(method="manual"),
            "qa": lambda child: child["qa"].update(status="passed"),
            "flags": lambda child: child["qa"]["flags"].remove(
                "BONE_BINDING_REVIEW_REQUIRED"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                manifest = deepcopy(self.preview_manifest)
                mutate(manifest["layers"][1])
                _path, digest = LayerManifestBundleStore(self.state).publish(
                    self.project["id"], manifest, self.assets
                )
                preview = deepcopy(self.preview)
                preview["layer_manifest_sha256"] = digest
                artifact = ImmutableJsonArtifactStore(self.state).publish(
                    "split-previews", self.project["id"], preview
                )
                self.assert_error(
                    "artifact_invalid", self.decision(digest=artifact.sha256)
                )

    def test_current_child_raster_uses_the_canonical_png_encoder(self) -> None:
        stored = self.bind(self.decision())
        with patch(
            "autospine_workbench.split_binding_target.encode_rgba_png",
            side_effect=lambda image: b"changed-encoder" + image.pixels,
        ):
            rebound = self.bind(stored, stored=True)
            self.assertEqual("stale", rebound[LAYER_ID]["binding_status"])
            self.assert_error("stale_artifact", self.decision())

    def test_split_rebuild_error_is_stale_without_leaking_name_error(self) -> None:
        stored = self.bind(self.decision())
        with patch(
            "autospine_workbench.split_binding_target.split_alpha_bilateral",
            side_effect=AlphaBilateralSplitError("synthetic split failure"),
        ):
            rebound = self.bind(stored, stored=True)
            self.assertEqual("stale", rebound[LAYER_ID]["binding_status"])
            self.assert_error("stale_artifact", self.decision())

    def test_missing_tampered_preview_or_manifest_bundle_is_a_hard_error(self) -> None:
        self.assert_error("artifact_missing", self.decision(digest="f" * 64))
        original = self.published.path.read_bytes()
        self.published.path.write_text("{}", encoding="utf-8")
        try:
            self.assert_error("artifact_invalid", self.decision())
        finally:
            self.published.path.write_bytes(original)

        missing_manifest = deepcopy(self.preview)
        missing_manifest["layer_manifest_sha256"] = "f" * 64
        published = ImmutableJsonArtifactStore(self.state).publish(
            "split-previews", self.project["id"], missing_manifest
        )
        self.assert_error("manifest_missing", self.decision(digest=published.sha256))

        child = (
            self.state
            / "builds"
            / self.project["id"]
            / "layer-manifests"
            / self.preview["layer_manifest_sha256"]
            / "layers"
            / f"{LAYER_ID}--left.png"
        )
        child_original = child.read_bytes()
        child.write_bytes(child_original + b"tamper")
        try:
            self.assert_error("manifest_invalid", self.decision())
        finally:
            child.write_bytes(child_original)

    def test_wrong_layer_and_unavailable_current_source_fail_closed(self) -> None:
        wrong = {"other-layer": self.decision()[LAYER_ID]}
        self.assert_error("wrong_layer", wrong)
        saved = self.sources.pop(LAYER_ID)
        try:
            self.assert_error("source_missing", self.decision())
        finally:
            self.sources[LAYER_ID] = saved

    @staticmethod
    def _stored_for(document: dict, digest: str) -> dict:
        algorithm = document["review_target"]["operation"]["algorithm"]
        return {
            LAYER_ID: {
                "action": "accept",
                "split_artifact_sha256": digest,
                "operation_config_sha256": document["operation_config_sha256"],
                "review_target_sha256": document["review_target_sha256"],
                "analysis": {
                    "algorithm_id": algorithm["id"],
                    "algorithm_version": algorithm["version"],
                    "layer_manifest_sha256": document["layer_manifest_sha256"],
                    "resolved_snapshot_sha256": document["resolved_snapshot_sha256"],
                    "split_spec_sha256": canonical_sha256(document["split_spec"]),
                },
                "binding_status": "current",
            }
        }


if __name__ == "__main__":
    unittest.main()
