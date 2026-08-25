"""Pure verified Spine 4.2 compilation and upstream-rebuild tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_source_images import (  # noqa: E402
    VerifiedAttachmentImage,
    VerifiedMeshSource,
)
from autospine_workbench.motion_retarget_bundle_integrity import (  # noqa: E402
    VerifiedMotionRetargetBundle,
)
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_bundle_contract import (  # noqa: E402
    build_spine42_bundle_contract,
)
from autospine_workbench.spine42_bundle_integrity import (  # noqa: E402
    VerifiedSpine42Bundle,
)
from autospine_workbench.spine42_pipeline import (  # noqa: E402
    VerifiedSpine42Pipeline,
    VerifiedSpine42PipelineError,
)
from tests.test_spine42_json_adapter import motion_pair, rig_fixture  # noqa: E402


PROJECT = "synthetic-p3"


def _json(value) -> str:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))


def mesh_source() -> VerifiedMeshSource:
    rig = rig_fixture()
    raws = (
        encode_rgba_png(RgbaImage(20, 30, bytes((10, 20, 30, 255)) * 600)),
        encode_rgba_png(RgbaImage(20, 40, bytes((40, 50, 60, 255)) * 800)),
    )
    images = []
    for attachment, raw in zip(rig["attachments"], raws):
        digest = hashlib.sha256(raw).hexdigest()
        attachment["image_sha256"] = digest
        width, height = ((20, 30) if attachment["type"] == "region" else (20, 40))
        images.append(VerifiedAttachmentImage(
            attachment["id"], attachment["image_path"], digest,
            width, height, raw,
        ))
    _target, instance_source = motion_pair(rig)
    p3_bundle = _target["source"]["p3"]["bundle_sha256"]
    return VerifiedMeshSource(
        Path("synthetic-p3"), PROJECT, canonical_sha256(rig), p3_bundle,
        "6" * 64, "7" * 64, _json(rig), tuple(images),
    )


def motion_bundle(mesh: VerifiedMeshSource) -> VerifiedMotionRetargetBundle:
    target, instance = motion_pair(mesh.rig)
    source = {
        "p3_rig_sha256": target["source"]["p3"]["rig_sha256"],
        "p3_bundle_sha256": target["source"]["p3"]["bundle_sha256"],
        "p4_profile_sha256": target["source"]["p4_profile_sha256"],
        "p4_bundle_sha256": target["source"]["p4_bundle_sha256"],
        "motion_clip_sha256": instance["source"]["motion_ir_sha256"],
        "motion_bundle_sha256": instance["source"]["motion_bundle_sha256"],
    }
    documents = tuple((name, _json(value).encode()) for name, value in (
        ("target-profile.json", target), ("instance.json", instance),
        ("run-manifest.json", {}), ("retarget-report.json", {}),
        ("mesh-regression.json", {}),
    ))
    return VerifiedMotionRetargetBundle(
        Path("synthetic-p5"), PROJECT, instance["clip_id"],
        canonical_sha256(target), canonical_sha256(instance),
        "a" * 64, "b" * 64, "c" * 64, "9" * 64,
        tuple(source.items()), documents,
    )


def verified_export(result, *, contract=None) -> VerifiedSpine42Bundle:
    values = result if contract is None else contract
    documents = tuple(values.document_bytes.items())
    return VerifiedSpine42Bundle(
        Path("synthetic-p6"), values.project_id, values.mode, values.clip_id,
        values.skeleton_json_sha256, values.atlas_sha256, values.png_sha256,
        values.run_identity_sha256, values.run_document_sha256,
        values.report_sha256, values.bundle_sha256, documents,
        tuple(values.source_image_sha256s.items()),
    )


class VerifiedSpine42PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh = mesh_source()
        self.motion = motion_bundle(self.mesh)

    def _build(self, root: Path, *, motion=False):
        kwargs = {}
        if motion:
            kwargs = {
                "motion_instance_sha256": self.motion.instance_sha256,
                "motion_bundle_sha256": self.motion.bundle_sha256,
            }
        with patch(
            "autospine_workbench.spine42_pipeline."
            "VerifiedMeshSourceReader.load", return_value=self.mesh,
        ) as mesh_load, patch(
            "autospine_workbench.spine42_pipeline."
            "VerifiedMotionRetargetBundleReader.load", return_value=self.motion,
        ) as motion_load:
            result = VerifiedSpine42Pipeline(root).build(
                PROJECT, self.mesh.p3_rig_sha256,
                self.mesh.p3_bundle_sha256, **kwargs,
            )
        mesh_load.assert_called_once_with(
            PROJECT, self.mesh.p3_rig_sha256, self.mesh.p3_bundle_sha256
        )
        self.assertEqual(motion, motion_load.called)
        return result

    def test_setup_build_is_deterministic_frozen_copy_isolated_and_pure(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self._build(root)
            second = self._build(root)
            self.assertEqual(first, second)
            self.assertEqual([], list(root.iterdir()))
        self.assertEqual("setup-only", first.mode)
        self.assertIsNone(first.p5_source)
        self.assertEqual(5, len(first.document_bytes))
        self.assertEqual(
            set(first.source_image_sha256s), {"face-image", "leg-mesh"}
        )
        changed = first.skeleton_json
        changed["bones"].clear()
        self.assertGreater(len(first.skeleton_json["bones"]), 0)
        documents = first.document_bytes
        documents.clear()
        self.assertEqual(5, len(first.document_bytes))
        sources = first.source_image_sha256s
        sources.clear()
        self.assertEqual(2, len(first.source_image_sha256s))
        with self.assertRaises(FrozenInstanceError):
            first.mode = "motion"  # type: ignore[misc]

    def test_motion_build_binds_exact_p3_and_p5_chain(self):
        with TemporaryDirectory() as temporary:
            result = self._build(Path(temporary), motion=True)
        self.assertEqual("motion", result.mode)
        self.assertEqual(self.motion.clip_id, result.clip_id)
        self.assertEqual(self.mesh.p3_address[1:], (
            result.p3_rig_sha256, result.p3_bundle_sha256,
        ))
        self.assertEqual(self.motion.instance_sha256,
                         result.p5_source["motion_instance_sha256"])
        self.assertEqual({self.motion.clip_id}, set(result.skeleton_json["animations"]))

    def test_incomplete_or_cross_p3_motion_address_fails_closed(self):
        pipeline = VerifiedSpine42Pipeline(Path("unused"))
        with self.assertRaisesRegex(VerifiedSpine42PipelineError, "together"):
            pipeline.build(
                PROJECT, self.mesh.p3_rig_sha256, self.mesh.p3_bundle_sha256,
                motion_instance_sha256=self.motion.instance_sha256,
            )
        wrong_sources = self.motion.source_addresses
        wrong_sources["p3_bundle_sha256"] = "f" * 64
        wrong = replace(self.motion, _source_items=tuple(wrong_sources.items()))
        with patch(
            "autospine_workbench.spine42_pipeline."
            "VerifiedMeshSourceReader.load", return_value=self.mesh,
        ), patch(
            "autospine_workbench.spine42_pipeline."
            "VerifiedMotionRetargetBundleReader.load", return_value=wrong,
        ), self.assertRaisesRegex(VerifiedSpine42PipelineError, "source chain"):
            pipeline.build(
                PROJECT, self.mesh.p3_rig_sha256, self.mesh.p3_bundle_sha256,
                motion_instance_sha256=wrong.instance_sha256,
                motion_bundle_sha256=wrong.bundle_sha256,
            )

    def test_rebuild_compares_all_five_files_against_exact_upstream(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            built = self._build(root, motion=True)
            bundle = verified_export(built)
            with patch(
                "autospine_workbench.spine42_pipeline."
                "VerifiedMeshSourceReader.load", return_value=self.mesh,
            ), patch(
                "autospine_workbench.spine42_pipeline."
                "VerifiedMotionRetargetBundleReader.load", return_value=self.motion,
            ):
                rebuilt = VerifiedSpine42Pipeline(root).rebuild_and_verify(bundle)
        self.assertEqual(built, rebuilt)
        self.assertEqual(bundle.document_bytes, rebuilt.document_bytes)

    def test_self_consistent_forged_export_cannot_bypass_upstream_rebuild(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            built = self._build(root)
            forged_json = deepcopy(built.skeleton_json)
            forged_json["skeleton"]["width"] += 1
            forged_contract = build_spine42_bundle_contract(
                PROJECT, built.p3_source, forged_json, built.atlas_bytes,
                built.png_bytes, built.source_image_sha256s,
            )
            self.assertNotEqual(built.document_bytes,
                                forged_contract.document_bytes)
            forged = verified_export(built, contract=forged_contract)
            with patch(
                "autospine_workbench.spine42_pipeline."
                "VerifiedMeshSourceReader.load", return_value=self.mesh,
            ), self.assertRaisesRegex(
                VerifiedSpine42PipelineError, "exact upstream rebuild"
            ):
                VerifiedSpine42Pipeline(root).rebuild_and_verify(forged)


if __name__ == "__main__":
    unittest.main()
