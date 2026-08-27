"""Pure exact-address MotionInstance v3 to Spine 4.2 compilation."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path
from typing import Any

from .mesh_source_images import VerifiedMeshSourceReader
from .motion_instance_v2_validation import require_motion_instance_v2
from .motion_instance_v3_bundle_integrity import replay_verified_motion_instance_v3_bundle
from .motion_instance_v3_bundle_reader import VerifiedMotionInstanceV3BundleReader
from .motion_retarget_bundle_reader import VerifiedMotionRetargetBundleReader
from .reviewed_motion_bundle_reader import VerifiedReviewedMotionBundleReader
from .spine42_atlas import build_spine42_atlas
from .spine42_json_adapter_v3 import build_spine42_json_v3
from .spine42_v3_bundle_contract import build_spine42_v3_bundle_contract
from .spine42_v3_bundle_integrity import VerifiedSpine42V3Bundle
from .spine42_v3_pipeline_result import VerifiedSpine42V3Compilation
from .spine42_v3_pipeline_chain import (
    require_digest_source as _digest_source,
    require_exact_spine42_v3_chain as _require_exact_chain,
    require_object as _object,
)


class VerifiedSpine42V3PipelineError(RuntimeError):
    """Raised when an exact MIv3 source chain cannot reproduce an export."""


class VerifiedSpine42V3Pipeline:
    """Compile only an explicit MIv3 address and never write state."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def build(
        self,
        project_id: str,
        motion_instance_v3_sha256: str,
        motion_instance_v3_bundle_sha256: str,
    ) -> VerifiedSpine42V3Compilation:
        """Replay MIv3/P9/P5/P3 and build one export entirely in memory."""

        try:
            v3 = VerifiedMotionInstanceV3BundleReader(self.state_root).load(
                project_id,
                motion_instance_v3_sha256,
                motion_instance_v3_bundle_sha256,
            )
            v3_run = _object(
                v3.document("run-manifest.json"), "MIv3 run"
            )
            p9_address = _digest_source(
                _object(_object(v3_run.get("inputs"), "MIv3 inputs").get(
                    "p9"
                ), "MIv3 P9 source"),
                ("motion_instance_v2_sha256", "bundle_sha256"),
                "MIv3 P9 source",
            )
            reviewed = VerifiedReviewedMotionBundleReader(self.state_root).load(
                project_id,
                p9_address["motion_instance_v2_sha256"],
                p9_address["bundle_sha256"],
            )
            replay_verified_motion_instance_v3_bundle(v3, reviewed)
            p9_run = _object(
                reviewed.document("run-manifest.json"), "P9 run"
            )
            p9_inputs = _object(p9_run.get("inputs"), "P9 inputs")
            motion_v2 = _object(
                reviewed.document("motion-instance-v2.json"),
                "MotionInstance v2",
            )
            require_motion_instance_v2(motion_v2)
            motion_v2_source = _object(
                motion_v2.get("source"), "MotionInstance v2 source"
            )
            p3 = {
                "rig_sha256": motion_v2_source.get("p3_rig_sha256"),
                "bundle_sha256": motion_v2_source.get("p3_bundle_sha256"),
            }
            p3 = _digest_source(
                p3, ("rig_sha256", "bundle_sha256"), "P3 source"
            )
            p5 = _digest_source(
                _object(p9_inputs.get("p5"), "P9 P5 source"),
                ("instance_sha256", "bundle_sha256",
                 "target_profile_sha256"),
                "P9 P5 source",
            )
            retarget = VerifiedMotionRetargetBundleReader(self.state_root).load(
                project_id, p5["instance_sha256"], p5["bundle_sha256"]
            )
            mesh = VerifiedMeshSourceReader(self.state_root).load(
                project_id, p3["rig_sha256"], p3["bundle_sha256"]
            )
            _require_exact_chain(
                project_id, motion_instance_v3_sha256,
                motion_instance_v3_bundle_sha256, v3, v3_run,
                reviewed, p9_run, motion_v2, p3, p5, retarget, mesh,
            )
            return _compile(v3, reviewed, retarget.target_profile, mesh)
        except VerifiedSpine42V3PipelineError:
            raise
        except (
            AttributeError, KeyError, OSError, OverflowError,
            RuntimeError, TypeError, UnicodeError, ValueError,
        ) as exc:
            raise VerifiedSpine42V3PipelineError(
                f"Verified Spine 4.2 v3 compilation failed: {exc}"
            ) from exc

    def rebuild_and_verify(
        self,
        expected: VerifiedSpine42V3Bundle | VerifiedSpine42V3Compilation,
    ) -> VerifiedSpine42V3Compilation:
        """Rebuild from exact MIv3 inputs and compare every public byte."""

        try:
            if type(expected) not in (
                VerifiedSpine42V3Bundle, VerifiedSpine42V3Compilation,
            ):
                raise VerifiedSpine42V3PipelineError(
                    "A verified Spine 4.2 v3 compilation is required"
                )
            rebuilt = self.build(
                expected.project_id,
                expected.motion_instance_v3_sha256,
                expected.motion_instance_v3_bundle_sha256,
            )
            if (
                rebuilt.clip_id != expected.clip_id
                or rebuilt.contract_identities
                != expected.contract_identities
                or rebuilt.source_image_sha256s
                != expected.source_image_sha256s
                or rebuilt.document_bytes != expected.document_bytes
            ):
                raise VerifiedSpine42V3PipelineError(
                    "Spine v3 export differs from exact upstream rebuild"
                )
            return rebuilt
        except VerifiedSpine42V3PipelineError:
            raise
        except (
            AttributeError, KeyError, OSError, OverflowError,
            RuntimeError, TypeError, UnicodeError, ValueError,
        ) as exc:
            raise VerifiedSpine42V3PipelineError(
                f"Verified Spine 4.2 v3 rebuild failed: {exc}"
            ) from exc


def _compile(v3: Any, reviewed: Any, target: Mapping[str, Any], mesh: Any):
    rig = mesh.rig
    images, source_hashes = _source_images(mesh)
    instance = v3.document("motion-instance-v3.json")
    admission = v3.document("body-sway-motion-consumer-admission.json")
    skeleton = build_spine42_json_v3(
        rig,
        motion_instance_v3=instance,
        admission=admission,
        reviewed_bundle=reviewed,
        motion_instance_v3_bundle_sha256=v3.bundle_sha256,
        target_profile=target,
    )
    atlas = build_spine42_atlas(images, page_name="skeleton.png")
    p3 = {
        "rig_sha256": mesh.p3_rig_sha256,
        "bundle_sha256": mesh.p3_bundle_sha256,
    }
    source = {
        "motion_instance_v3_sha256": v3.motion_instance_v3_sha256,
        "bundle_sha256": v3.bundle_sha256,
        "admission_sha256": v3.admission_sha256,
        "profile_sha256": v3.motion_instance_v3_profile_sha256,
        "target_profile_sha256": v3.target_profile_sha256,
    }
    contract = build_spine42_v3_bundle_contract(
        mesh.project_id, v3.clip_id, p3, source, skeleton,
        atlas.atlas_bytes, atlas.png_bytes, source_hashes,
    )
    return VerifiedSpine42V3Compilation.from_contract(contract)


def _source_images(mesh: Any) -> tuple[dict[str, bytes], dict[str, str]]:
    images: dict[str, bytes] = {}
    identities: dict[str, str] = {}
    for item in mesh.images:
        if item.attachment_id in images or type(item.png_bytes) is not bytes:
            raise VerifiedSpine42V3PipelineError(
                "P3 source image inventory is invalid"
            )
        digest = hashlib.sha256(item.png_bytes).hexdigest()
        if digest != item.image_sha256:
            raise VerifiedSpine42V3PipelineError(
                "P3 source image identity differs"
            )
        images[item.attachment_id] = item.png_bytes
        identities[item.attachment_id] = digest
    attachments = mesh.rig["attachments"]
    expected = {item["id"]: item["image_sha256"] for item in attachments}
    if len(expected) != len(attachments) or identities != expected:
        raise VerifiedSpine42V3PipelineError(
            "P3 attachment and source image identities differ"
        )
    return images, identities


__all__ = ["VerifiedSpine42V3Pipeline", "VerifiedSpine42V3PipelineError"]
