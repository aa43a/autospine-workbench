"""P10.5a exact static seam-anchor input closure tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.ik_target_geometry import (  # noqa: E402
    SOURCE_IDENTITY_FIELDS,
)
from autospine_workbench.manifest_bundle import (  # noqa: E402
    LayerManifestBundleReader,
)
from autospine_workbench.mesh_bundle_admission import (  # noqa: E402
    require_exact_mesh_bundle,
)
from autospine_workbench.mesh_source_from_bundle import (  # noqa: E402
    verified_mesh_source_from_bundle,
)
from autospine_workbench.seam_anchor_inputs import (  # noqa: E402
    SeamAnchorInputError,
    require_seam_anchor_inputs,
)
from autospine_workbench.seam_anchor_profile import (  # noqa: E402
    ATTACHMENT_IMAGE_SET_HASH_DOMAIN,
    SEAM_SOURCE_IDENTITY_FIELDS,
    SeamAnchorProfileError,
    attachment_image_set_sha256,
    seam_anchor_resource_limits,
)
from tests.p10_candidate_helpers import P10PersistedFixture  # noqa: E402


def _reverse_keys(value):
    if isinstance(value, dict):
        return {
            key: _reverse_keys(item)
            for key, item in reversed(list(value.items()))
        }
    if isinstance(value, list):
        return [_reverse_keys(item) for item in value]
    return value


class SeamAnchorInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = P10PersistedFixture(Path(cls.temporary.name))
        cls.manifest = LayerManifestBundleReader(cls.fixture.state).load(
            cls.fixture.mesh.project_id,
            cls.fixture.layer_manifest_sha256,
        ).manifest
        cls.inputs = require_seam_anchor_inputs(
            cls.manifest, cls.fixture.mesh
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_deterministic_frozen_copy_isolated_and_replays_both_boundaries(self):
        first = self.inputs
        second = require_seam_anchor_inputs(
            _reverse_keys(self.manifest), self.fixture.mesh
        )
        self.assertEqual(first, second)
        with patch(
            "autospine_workbench.seam_anchor_source."
            "require_exact_mesh_bundle",
            wraps=require_exact_mesh_bundle,
        ) as exact, patch(
            "autospine_workbench.seam_anchor_source."
            "verified_mesh_source_from_bundle",
            wraps=verified_mesh_source_from_bundle,
        ) as source:
            replayed = require_seam_anchor_inputs(
                self.manifest, self.fixture.mesh
            )
        self.assertEqual(first, replayed)
        exact.assert_called_once_with(self.fixture.mesh)
        source.assert_called_once_with(
            self.fixture.mesh, image_budget=unittest.mock.ANY
        )

        manifest = first.manifest
        manifest.clear()
        rig = first.rig
        rig.clear()
        images = first.attachment_images
        images[0].clear()
        pngs = first.png_by_attachment
        pngs.clear()
        source_value = first.source
        source_value.clear()
        self.assertTrue(first.manifest)
        self.assertTrue(first.rig)
        self.assertTrue(first.attachment_images[0])
        self.assertTrue(first.png_by_attachment)
        self.assertTrue(first.source)
        with self.assertRaises(FrozenInstanceError):
            first.project_id = "changed"  # type: ignore[misc]

    def test_source_is_static_complete_and_image_bytes_are_frozen(self):
        source = self.inputs.source
        self.assertEqual(set(SEAM_SOURCE_IDENTITY_FIELDS), set(source))
        for field in SOURCE_IDENTITY_FIELDS:
            self.assertEqual(getattr(self.fixture.mesh, field), source[field])
        self.assertEqual(
            self.inputs.attachment_image_set_sha256,
            source["attachment_image_set_sha256"],
        )
        self.assertFalse(any(
            token in key.casefold()
            for key in source for token in ("clip", "motion", "p10")
        ))
        self.assertNotIn("path", source)
        for metadata in self.inputs.attachment_images:
            raw = self.inputs.png_by_attachment[metadata["attachment_id"]]
            self.assertEqual(
                metadata["image_sha256"], hashlib.sha256(raw).hexdigest()
            )

    def test_image_set_hash_is_canonical_and_domain_separated(self):
        rows = list(self.inputs.attachment_images)
        baseline = attachment_image_set_sha256(rows)
        self.assertEqual(baseline, attachment_image_set_sha256(rows[::-1]))
        self.assertEqual(
            "autospine-seam-anchor-attachment-image-set/v1",
            ATTACHMENT_IMAGE_SET_HASH_DOMAIN,
        )
        for field, value in (
            ("attachment_id", "changed-id"),
            ("image_path", "layers/changed.png"),
            ("image_sha256", "f" * 64),
            ("width", rows[0]["width"] + 1),
            ("height", rows[0]["height"] + 1),
        ):
            changed = deepcopy(rows)
            changed[0][field] = value
            with self.subTest(field=field):
                self.assertNotEqual(
                    baseline, attachment_image_set_sha256(changed)
                )
        with patch(
            "autospine_workbench.seam_anchor_profile."
            "ATTACHMENT_IMAGE_SET_HASH_DOMAIN",
            "autospine-seam-anchor-attachment-image-set/test",
        ):
            self.assertNotEqual(baseline, attachment_image_set_sha256(rows))

    def test_manifest_shape_coordinate_project_and_sha_fail_closed(self):
        attacks = []
        for location in ((), ("source",), ("source", "coordinate_system")):
            changed = deepcopy(self.manifest)
            target = changed
            for key in location:
                target = target[key]
            target["unsupported"] = True
            attacks.append(changed)
        changed = deepcopy(self.manifest)
        changed["source"]["coordinate_system"]["y_axis"] = "up"
        attacks.append(changed)
        changed = deepcopy(self.manifest)
        changed["project_id"] = "other-project"
        attacks.append(changed)
        changed = deepcopy(self.manifest)
        changed["revision"] += 1
        attacks.append(changed)
        changed = deepcopy(self.manifest)
        changed["layers"][0]["raster"]["sha256"] = "f" * 64
        attacks.append(changed)
        changed = deepcopy(self.manifest)
        changed["layers"][0]["semantic"]["side"] = "viewer-left"
        attacks.append(changed)
        changed = deepcopy(self.manifest)
        changed["layers"][0]["rig_hint"]["attachment_kind"] = "video"
        attacks.append(changed)
        changed = deepcopy(self.manifest)
        changed["source"]["relative_path"] = "../outside.psd"
        attacks.append(changed)
        for status in ("manual_required", "rejected"):
            changed = deepcopy(self.manifest)
            changed["qa"]["status"] = status
            attacks.append(changed)
        for attack in attacks:
            with self.subTest(attack=attack), self.assertRaises(
                SeamAnchorInputError
            ):
                require_seam_anchor_inputs(attack, self.fixture.mesh)

    def test_p3_identity_source_bytes_and_types_fail_closed(self):
        forged_values = (
            replace(self.fixture.mesh, rig_sha256="f" * 64),
            replace(self.fixture.mesh, resolved_project_sha256="f" * 64),
            replace(self.fixture.mesh, layer_manifest_sha256="f" * 64),
        )
        for forged in forged_values:
            with self.subTest(forged=forged), self.assertRaises(
                SeamAnchorInputError
            ):
                require_seam_anchor_inputs(self.manifest, forged)
        path, raw = self.fixture.mesh._source_png_items[0]
        damaged = replace(
            self.fixture.mesh,
            _source_png_items=((path, raw + b"tamper"),)
            + self.fixture.mesh._source_png_items[1:],
        )
        with self.assertRaises(SeamAnchorInputError):
            require_seam_anchor_inputs(self.manifest, damaged)
        for manifest, bundle in (
            ([], self.fixture.mesh),
            (self.manifest, object()),
        ):
            with self.subTest(type=type(bundle)), self.assertRaises(
                SeamAnchorInputError
            ):
                require_seam_anchor_inputs(manifest, bundle)  # type: ignore[arg-type]

    def test_all_explicit_resource_budgets_fail_closed(self):
        rows = self.inputs.attachment_images
        pngs = self.inputs.png_by_attachment
        cases = (
            ("MAX_LAYER_MANIFEST_BYTES", 1),
            ("MAX_RIG_IR_BYTES", 1),
            ("MAX_MANIFEST_LAYERS", len(self.manifest["layers"]) - 1),
            ("MAX_ATTACHMENTS", len(rows) - 1),
            ("MAX_ATTACHMENT_PNG_BYTES", max(map(len, pngs.values())) - 1),
            ("MAX_TOTAL_ATTACHMENT_PNG_BYTES", sum(map(len, pngs.values())) - 1),
            ("MAX_ATTACHMENT_PIXELS", max(
                row["width"] * row["height"] for row in rows
            ) - 1),
            ("MAX_TOTAL_ATTACHMENT_PIXELS", sum(
                row["width"] * row["height"] for row in rows
            ) - 1),
        )
        for name, maximum in cases:
            with self.subTest(name=name), patch(
                f"autospine_workbench.seam_anchor_profile.{name}", maximum
            ), self.assertRaisesRegex(SeamAnchorInputError, "resource limit"):
                require_seam_anchor_inputs(self.manifest, self.fixture.mesh)

    def test_profile_rejects_noncanonical_image_metadata(self):
        rows = list(self.inputs.attachment_images)
        attacks = (
            object(),
            [{**rows[0], "extra": True}],
            [rows[0], dict(rows[0])],
            [{**rows[0], "width": True}],
            [{**rows[0], "image_path": "../escape.png"}],
        )
        for attack in attacks:
            with self.subTest(attack=attack), self.assertRaises(
                SeamAnchorProfileError
            ):
                attachment_image_set_sha256(attack)  # type: ignore[arg-type]
        limits = seam_anchor_resource_limits()
        limits.clear()
        self.assertTrue(seam_anchor_resource_limits())


if __name__ == "__main__":
    unittest.main()
