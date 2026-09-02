"""Pure exact P10.6b v2 to Spine 4.2 compilation pipeline."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .mesh_source_images import VerifiedMeshSourceReader
from .motion_instance_v2_validation import require_motion_instance_v2
from .motion_instance_v3_bundle_reader_v2 import (
    MotionInstanceV3BundleReaderV2, VerifiedMotionInstanceV3BundleV2,
)
from .motion_retarget_bundle_reader import VerifiedMotionRetargetBundleReader
from .reviewed_motion_bundle_reader import VerifiedReviewedMotionBundleReader
from .spine42_atlas import build_spine42_atlas
from .spine42_contract_v3_v2 import spine42_motion_source_v3_v2
from .spine42_json_adapter_v3_v2 import build_spine42_json_v3_v2
from .spine42_v3_bundle_contract_v2 import (
    build_spine42_v3_bundle_contract_v2,
)
from .spine42_v3_pipeline_chain_v2 import (
    require_digest_source as _digest_source,
    require_exact_spine42_v3_chain_v2 as _require_exact_chain,
    require_object as _object,
)
from .spine42_v3_pipeline_result_v2 import (
    VerifiedSpine42V3CompilationV2,
)


class VerifiedSpine42V3PipelineV2Error(RuntimeError):
    pass


class VerifiedSpine42V3PipelineV2:
    """Build only an explicit P10.6b v2 address and never inspect heads."""

    def __init__(self, state_root: Path):
        self.state_root = Path(state_root)

    def build(
        self, project_id: str, motion_instance_v3_sha256: str,
        motion_instance_v3_bundle_sha256: str,
    ) -> VerifiedSpine42V3CompilationV2:
        """Exact-read P10.6b v2/P9/P5/P3 and compile fully in memory."""

        try:
            v3 = MotionInstanceV3BundleReaderV2(self.state_root).load(
                project_id, motion_instance_v3_sha256,
                motion_instance_v3_bundle_sha256,
            )
            return self._build_issued(v3)
        except VerifiedSpine42V3PipelineV2Error:
            raise
        except (
            AttributeError, KeyError, OSError, OverflowError,
            RuntimeError, TypeError, UnicodeError, ValueError,
        ) as exc:
            raise VerifiedSpine42V3PipelineV2Error(
                f"Verified Spine 4.2 v2-source compilation failed: {exc}"
            ) from exc

    def build_from_verified(
        self, motion_bundle: VerifiedMotionInstanceV3BundleV2,
    ) -> VerifiedSpine42V3CompilationV2:
        """Compile one already exact-read source without reading it again."""

        try:
            return self._build_issued(motion_bundle)
        except VerifiedSpine42V3PipelineV2Error:
            raise
        except (
            AttributeError, KeyError, OSError, OverflowError,
            RuntimeError, TypeError, UnicodeError, ValueError,
        ) as exc:
            raise VerifiedSpine42V3PipelineV2Error(
                f"Verified Spine 4.2 v2-source compilation failed: {exc}"
            ) from exc

    def _build_issued(self, v3):
        if type(v3) is not VerifiedMotionInstanceV3BundleV2:
            raise VerifiedSpine42V3PipelineV2Error(
                "P10.7a v2 source is not reader-issued"
            )
        project_id = v3.project_id
        motion_instance_v3_sha256 = v3.motion_instance_v3_sha256
        motion_instance_v3_bundle_sha256 = v3.bundle_sha256
        v3_run = _object(
            v3.document("run-manifest-v2.json"), "P10.6b v2 run",
        )
        p9 = _digest_source(
            _object(_object(v3_run.get("inputs"), "P10.6b inputs").get(
                "p9"
            ), "P10.6b P9 source"),
            ("motion_instance_v2_sha256", "bundle_sha256"),
            "P10.6b P9 source",
        )
        reviewed = VerifiedReviewedMotionBundleReader(
            self.state_root
        ).load(
            project_id, p9["motion_instance_v2_sha256"],
            p9["bundle_sha256"],
        )
        p9_run = _object(
            reviewed.document("run-manifest.json"), "P9 run",
        )
        p9_inputs = _object(p9_run.get("inputs"), "P9 inputs")
        motion_v2 = _object(
            reviewed.document("motion-instance-v2.json"),
            "MotionInstance v2",
        )
        require_motion_instance_v2(motion_v2)
        motion_source = _object(
            motion_v2.get("source"), "MotionInstance v2 source",
        )
        p3 = _digest_source({
            "rig_sha256": motion_source.get("p3_rig_sha256"),
            "bundle_sha256": motion_source.get("p3_bundle_sha256"),
        }, ("rig_sha256", "bundle_sha256"), "P3 source")
        p5 = _digest_source(
            _object(p9_inputs.get("p5"), "P9 P5 source"),
            ("instance_sha256", "bundle_sha256",
             "target_profile_sha256"), "P9 P5 source",
        )
        retarget = VerifiedMotionRetargetBundleReader(
            self.state_root
        ).load(project_id, p5["instance_sha256"], p5["bundle_sha256"])
        mesh = VerifiedMeshSourceReader(self.state_root).load(
            project_id, p3["rig_sha256"], p3["bundle_sha256"],
        )
        _require_exact_chain(
            project_id, motion_instance_v3_sha256,
            motion_instance_v3_bundle_sha256, v3, v3_run,
            reviewed, p9_run, motion_v2, p3, p5, retarget, mesh,
        )
        return _compile(v3, reviewed, retarget.target_profile, mesh)

    def rebuild_and_verify(
        self, expected: VerifiedSpine42V3CompilationV2,
    ) -> VerifiedSpine42V3CompilationV2:
        """Historically rebuild one pure result; never observe current heads."""

        try:
            if type(expected) is not VerifiedSpine42V3CompilationV2:
                raise VerifiedSpine42V3PipelineV2Error(
                    "A verified P10.7a v2 compilation is required"
                )
            rebuilt = self.build(
                expected.project_id, expected.motion_instance_v3_sha256,
                expected.motion_instance_v3_bundle_sha256,
            )
            if rebuilt.clip_id != expected.clip_id \
                    or rebuilt.contract_identities \
                        != expected.contract_identities \
                    or rebuilt.source_image_sha256s \
                        != expected.source_image_sha256s \
                    or rebuilt.document_bytes != expected.document_bytes:
                raise VerifiedSpine42V3PipelineV2Error(
                    "P10.7a v2 export differs from exact upstream rebuild"
                )
            return rebuilt
        except VerifiedSpine42V3PipelineV2Error:
            raise
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            raise VerifiedSpine42V3PipelineV2Error(
                f"Verified Spine 4.2 v2-source rebuild failed: {exc}"
            ) from exc


def _compile(v3, reviewed, target, mesh):
    images, source_hashes = _source_images(mesh)
    skeleton = build_spine42_json_v3_v2(
        mesh.rig, motion_bundle=v3, reviewed_bundle=reviewed,
        target_profile=target,
    )
    atlas = build_spine42_atlas(images, page_name="skeleton.png")
    contract = build_spine42_v3_bundle_contract_v2(
        mesh.project_id, v3.clip_id,
        {"rig_sha256": mesh.p3_rig_sha256,
         "bundle_sha256": mesh.p3_bundle_sha256},
        spine42_motion_source_v3_v2(v3), skeleton,
        atlas.atlas_bytes, atlas.png_bytes, source_hashes,
    )
    return VerifiedSpine42V3CompilationV2.from_contract(contract)


def _source_images(mesh):
    images, identities = {}, {}
    for item in mesh.images:
        if item.attachment_id in images or type(item.png_bytes) is not bytes:
            raise VerifiedSpine42V3PipelineV2Error(
                "P3 source image inventory is invalid"
            )
        digest = hashlib.sha256(item.png_bytes).hexdigest()
        if digest != item.image_sha256:
            raise VerifiedSpine42V3PipelineV2Error(
                "P3 source image identity differs"
            )
        images[item.attachment_id] = item.png_bytes
        identities[item.attachment_id] = digest
    attachments = mesh.rig["attachments"]
    expected = {item["id"]: item["image_sha256"] for item in attachments}
    if len(expected) != len(attachments) or identities != expected:
        raise VerifiedSpine42V3PipelineV2Error(
            "P3 attachment and source image identities differ"
        )
    return images, identities


__all__ = [
    "VerifiedSpine42V3PipelineV2", "VerifiedSpine42V3PipelineV2Error",
]
