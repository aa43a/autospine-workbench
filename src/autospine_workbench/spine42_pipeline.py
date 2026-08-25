"""Pure verified P3/P5 to Spine 4.2 five-file compilation."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path
from typing import Any

from .mesh_source_images import VerifiedMeshSourceReader
from .motion_retarget_bundle_reader import VerifiedMotionRetargetBundleReader
from .resolved_project import canonical_sha256
from .spine42_atlas import build_spine42_atlas
from .spine42_bundle_contract import build_spine42_bundle_contract
from .spine42_bundle_integrity import VerifiedSpine42Bundle
from .spine42_json_adapter import build_spine42_json
from .spine42_pipeline_result import VerifiedSpine42Compilation


class VerifiedSpine42PipelineError(RuntimeError):
    """Raised when exact upstream artifacts cannot reproduce an export."""


class VerifiedSpine42Pipeline:
    """Compile only explicit content addresses and never write state."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def build(
        self,
        project_id: str,
        p3_rig_sha256: str,
        p3_bundle_sha256: str,
        *,
        motion_instance_sha256: str | None = None,
        motion_bundle_sha256: str | None = None,
    ) -> VerifiedSpine42Compilation:
        """Build one setup-only or animated export entirely in memory."""

        try:
            _require_motion_pair(motion_instance_sha256, motion_bundle_sha256)
            mesh = VerifiedMeshSourceReader(self.state_root).load(
                project_id, p3_rig_sha256, p3_bundle_sha256
            )
            _require_mesh_identity(
                mesh, project_id, p3_rig_sha256, p3_bundle_sha256
            )
            motion = self._load_motion(
                project_id, p3_rig_sha256, p3_bundle_sha256,
                motion_instance_sha256, motion_bundle_sha256,
            )
            return _compile(mesh, motion)
        except VerifiedSpine42PipelineError:
            raise
        except (AttributeError, KeyError, OverflowError, RuntimeError,
                TypeError, UnicodeError, ValueError) as exc:
            raise VerifiedSpine42PipelineError(
                f"Verified Spine 4.2 compilation failed: {exc}"
            ) from exc

    def rebuild_and_verify(
        self, bundle: VerifiedSpine42Bundle
    ) -> VerifiedSpine42Compilation:
        """Rebuild from run inputs and compare every byte and public identity."""

        try:
            if not isinstance(bundle, VerifiedSpine42Bundle):
                raise VerifiedSpine42PipelineError(
                    "A verified Spine 4.2 bundle is required"
                )
            p3, p5 = _run_sources(bundle)
            rebuilt = self.build(
                bundle.project_id, p3["rig_sha256"], p3["bundle_sha256"],
                motion_instance_sha256=(
                    None if p5 is None else p5["motion_instance_sha256"]
                ),
                motion_bundle_sha256=(
                    None if p5 is None else p5["bundle_sha256"]
                ),
            )
            _require_rebuild_matches(rebuilt, bundle, p3, p5)
            return rebuilt
        except VerifiedSpine42PipelineError:
            raise
        except (AttributeError, KeyError, RuntimeError, TypeError,
                UnicodeError, ValueError) as exc:
            raise VerifiedSpine42PipelineError(
                f"Verified Spine 4.2 rebuild failed: {exc}"
            ) from exc

    def _load_motion(
        self, project_id: str, p3_rig_sha256: str, p3_bundle_sha256: str,
        instance_sha256: str | None, bundle_sha256: str | None,
    ) -> Any | None:
        if instance_sha256 is None:
            return None
        motion = VerifiedMotionRetargetBundleReader(self.state_root).load(
            project_id, instance_sha256, bundle_sha256
        )
        if motion.project_id != project_id \
                or motion.instance_sha256 != instance_sha256 \
                or motion.bundle_sha256 != bundle_sha256:
            raise VerifiedSpine42PipelineError("P5 reader identity differs")
        sources = motion.source_addresses
        if sources.get("p3_rig_sha256") != p3_rig_sha256 \
                or sources.get("p3_bundle_sha256") != p3_bundle_sha256:
            raise VerifiedSpine42PipelineError(
                "P5 source chain differs from the requested P3 bundle"
            )
        if canonical_sha256(motion.target_profile) != motion.target_profile_sha256 \
                or canonical_sha256(motion.motion_instance) != motion.instance_sha256:
            raise VerifiedSpine42PipelineError("P5 document identity differs")
        return motion


def _compile(mesh: Any, motion: Any | None) -> VerifiedSpine42Compilation:
    rig = mesh.rig
    images, source_hashes = _source_images(mesh)
    instance = None if motion is None else motion.motion_instance
    profile = None if motion is None else motion.target_profile
    skeleton = build_spine42_json(
        rig, motion_instance=instance, target_profile=profile
    )
    atlas = build_spine42_atlas(images, page_name="skeleton.png")
    p3 = {"rig_sha256": mesh.p3_rig_sha256,
          "bundle_sha256": mesh.p3_bundle_sha256}
    p5 = _p5_source(motion)
    contract = build_spine42_bundle_contract(
        mesh.project_id, p3, skeleton, atlas.atlas_bytes, atlas.png_bytes,
        source_hashes, p5_source=p5,
    )
    return VerifiedSpine42Compilation(
        contract.project_id, contract.mode, contract.clip_id,
        contract.p3_rig_sha256, contract.p3_bundle_sha256,
        None if motion is None else motion.target_profile_sha256,
        contract.motion_instance_sha256,
        None if motion is None else motion.bundle_sha256,
        contract.skeleton_json_sha256, contract.atlas_sha256,
        contract.png_sha256, contract.run_identity_sha256,
        contract.run_document_sha256, contract.report_sha256,
        contract.bundle_sha256, tuple(contract.document_bytes.items()),
        tuple(sorted(contract.source_image_sha256s.items())),
    )


def _source_images(mesh: Any) -> tuple[dict[str, bytes], dict[str, str]]:
    images: dict[str, bytes] = {}
    identities: dict[str, str] = {}
    for item in mesh.images:
        if item.attachment_id in images or type(item.png_bytes) is not bytes:
            raise VerifiedSpine42PipelineError("P3 source image inventory is invalid")
        digest = hashlib.sha256(item.png_bytes).hexdigest()
        if digest != item.image_sha256:
            raise VerifiedSpine42PipelineError("P3 source image identity differs")
        images[item.attachment_id] = item.png_bytes
        identities[item.attachment_id] = digest
    attachments = mesh.rig["attachments"]
    expected = {item["id"]: item["image_sha256"] for item in attachments}
    if len(expected) != len(attachments) or identities != expected:
        raise VerifiedSpine42PipelineError(
            "P3 attachment and source image identities differ"
        )
    return images, identities


def _p5_source(motion: Any | None) -> dict[str, str] | None:
    if motion is None:
        return None
    return {
        "target_profile_sha256": motion.target_profile_sha256,
        "motion_instance_sha256": motion.instance_sha256,
        "bundle_sha256": motion.bundle_sha256,
        "clip_id": motion.clip_id,
    }


def _require_mesh_identity(mesh, project, rig_sha, bundle_sha) -> None:
    if mesh.project_id != project or mesh.p3_rig_sha256 != rig_sha \
            or mesh.p3_bundle_sha256 != bundle_sha \
            or canonical_sha256(mesh.rig) != rig_sha:
        raise VerifiedSpine42PipelineError("P3 reader identity differs")


def _require_motion_pair(instance, bundle) -> None:
    if (instance is None) != (bundle is None):
        raise VerifiedSpine42PipelineError(
            "P5 instance and bundle addresses must be supplied together"
        )


def _run_sources(bundle) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
    inputs = bundle.run_manifest.get("inputs")
    if type(inputs) is not dict or set(inputs) != {"p3", "p5", "source_images"}:
        raise VerifiedSpine42PipelineError("Export run inputs are invalid")
    p3, p5 = inputs["p3"], inputs["p5"]
    if type(p3) is not dict or set(p3) != {"rig_sha256", "bundle_sha256"}:
        raise VerifiedSpine42PipelineError("Export P3 run inputs are invalid")
    if p5 is not None and (type(p5) is not dict or set(p5) != {
        "target_profile_sha256", "motion_instance_sha256", "bundle_sha256", "clip_id",
    }):
        raise VerifiedSpine42PipelineError("Export P5 run inputs are invalid")
    return p3, p5


def _require_rebuild_matches(rebuilt, bundle, p3, p5) -> None:
    expected = {
        "skeleton_json_sha256": bundle.skeleton_json_sha256,
        "atlas_sha256": bundle.atlas_sha256, "png_sha256": bundle.png_sha256,
        "run_identity_sha256": bundle.run_identity_sha256,
        "run_document_sha256": bundle.run_document_sha256,
        "report_sha256": bundle.report_sha256,
        "bundle_sha256": bundle.bundle_sha256,
    }
    if rebuilt.p3_source != dict(p3) or rebuilt.p5_source != p5 \
            or rebuilt.mode != bundle.mode or rebuilt.clip_id != bundle.clip_id \
            or rebuilt.contract_identities != expected \
            or rebuilt.document_bytes != bundle.document_bytes:
        raise VerifiedSpine42PipelineError(
            "Spine bundle differs from exact upstream rebuild"
        )
