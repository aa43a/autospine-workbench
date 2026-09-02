"""One-pass P10.5d/P9 preparation for the P10.6b v2 compiler."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
import json
from typing import Any

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    VerifiedBodySwayDynamicSeamBundleV2,
)
from .body_sway_dynamic_seam_head_checks_v2 import (
    BodySwayDynamicSeamHeadObservationV2,
)
from .body_sway_motion_consumer_admission_v2 import (
    BodySwayMotionConsumerAdmissionCoreV2,
    BodySwayMotionConsumerAdmissionV2Error,
    seal_body_sway_motion_consumer_admission_v2,
)
from .body_sway_motion_consumer_core_v2 import (
    _compile_admitted_body_sway_motion_consumer_core_v2,
)
from .body_sway_motion_consumer_source_v2 import (
    BodySwayMotionConsumerSourceV2Error,
    admit_body_sway_motion_consumer_source_v2,
)
from .motion_instance_v3_prepared_checks_v2 import (
    body_sway_admission_observations_v2,
    bounded_body_sway_admission_v2,
    replay_body_sway_admission_with_core_v2,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import canonical_json_bytes


class MotionInstanceV3PreparedV2Error(ValueError):
    """Raised when exact P10.5d/P9 inputs cannot form one v2 source."""


def _build_prepared_api():
    """Keep issuance state out of the module namespace.

    This rejects ordinary direct construction and ``dataclasses.replace``;
    it is a provenance boundary, not a sandbox against hostile in-process
    Python introspection. Every untrusted JSON input is still replayed.
    """

    receipt = object()

    @dataclass(frozen=True, slots=True)
    class MotionInstanceV3PreparedCoreV2:
        project_id: str
        clip_id: str
        dynamic_seam_probe_sha256: str
        dynamic_seam_bundle_sha256: str
        motion_instance_v2_sha256: str
        reviewed_motion_bundle_sha256: str
        _consumer_core: BodySwayMotionConsumerAdmissionCoreV2 = field(
            repr=False
        )
        _motion_json: str = field(repr=False)
        _receipt: InitVar[object] = None

        def __post_init__(self, _receipt: object) -> None:
            if _receipt is not receipt:
                raise MotionInstanceV3PreparedV2Error(
                    "Prepared v2 core must be issued by the exact pipeline"
                )

    @dataclass(frozen=True, slots=True)
    class PreparedMotionInstanceV3V2:
        project_id: str
        clip_id: str
        dynamic_seam_probe_sha256: str
        dynamic_seam_bundle_sha256: str
        motion_instance_v2_sha256: str
        reviewed_motion_bundle_sha256: str
        admission_sha256: str
        _admission_json: str = field(repr=False)
        _motion_json: str = field(repr=False)
        _receipt: InitVar[object] = None

        def __post_init__(self, _receipt: object) -> None:
            if _receipt is not receipt:
                raise MotionInstanceV3PreparedV2Error(
                    "Prepared v2 source must be issued by the exact pipeline"
                )

        @property
        def admission(self) -> dict[str, Any]:
            return json.loads(self._admission_json)

        @property
        def admission_bytes(self) -> bytes:
            return self._admission_json.encode("utf-8")

        @property
        def motion_instance_v2(self) -> dict[str, Any]:
            return json.loads(self._motion_json)

    def compile_motion_instance_v3_prepared_core_v2(
        dynamic_bundle: VerifiedBodySwayDynamicSeamBundleV2,
        reviewed_bundle: VerifiedReviewedMotionBundle,
    ) -> MotionInstanceV3PreparedCoreV2:
        """Replay P10.5d/P9 once and build the unchanged P10.6a core."""

        try:
            admitted = admit_body_sway_motion_consumer_source_v2(
                dynamic_bundle, reviewed_bundle,
            )
            core = _compile_admitted_body_sway_motion_consumer_core_v2(
                admitted
            )
            source, p9 = admitted.source, admitted.source["p9"]
            address = (
                dynamic_bundle.project_id, dynamic_bundle.clip_id,
                dynamic_bundle.probe_sha256, dynamic_bundle.bundle_sha256,
                reviewed_bundle.motion_instance_v2_sha256,
                reviewed_bundle.bundle_sha256,
            )
            expected = (
                admitted.project_id, admitted.clip_id,
                source["dynamic_seam_probe_sha256"],
                source["dynamic_seam_bundle_sha256"],
                p9["motion_instance_v2_sha256"], p9["bundle_sha256"],
            )
            if address != expected:
                raise MotionInstanceV3PreparedV2Error(
                    "Prepared v2 source differs from its exact addresses"
                )
            return MotionInstanceV3PreparedCoreV2(
                *address, core,
                canonical_json_bytes(
                    admitted.motion_instance_v2
                ).decode("utf-8"),
                receipt,
            )
        except MotionInstanceV3PreparedV2Error:
            raise
        except (
            AttributeError, BodySwayMotionConsumerAdmissionV2Error,
            BodySwayMotionConsumerSourceV2Error, KeyError, OverflowError,
            RecursionError, RuntimeError, TypeError, UnicodeError, ValueError,
        ) as exc:
            raise MotionInstanceV3PreparedV2Error(
                f"MotionInstance v3 v2 source preparation failed: {exc}"
            ) from exc

    def seal_motion_instance_v3_prepared_v2(
        core: MotionInstanceV3PreparedCoreV2,
        before: BodySwayDynamicSeamHeadObservationV2,
        after: BodySwayDynamicSeamHeadObservationV2,
        *, expected_admission: Mapping[str, Any] | None = None,
    ) -> PreparedMotionInstanceV3V2:
        """Seal P10.6a and optionally match historical admission bytes."""

        try:
            if type(core) is not MotionInstanceV3PreparedCoreV2:
                raise MotionInstanceV3PreparedV2Error(
                    "MotionInstance v3 v2 requires an issued prepared core"
                )
            admission = seal_body_sway_motion_consumer_admission_v2(
                core._consumer_core, before, after,
            )
            replayed = replay_body_sway_admission_with_core_v2(
                core._consumer_core, admission.document,
            )
            if replayed != admission.canonical_bytes:
                raise MotionInstanceV3PreparedV2Error(
                    "P10.6a v2 admission differs from detached replay"
                )
            if expected_admission is not None \
                    and replayed != canonical_json_bytes(
                        bounded_body_sway_admission_v2(expected_admission)
                    ):
                raise MotionInstanceV3PreparedV2Error(
                    "P10.6a v2 admission differs from exact replay"
                )
            return PreparedMotionInstanceV3V2(
                core.project_id, core.clip_id,
                core.dynamic_seam_probe_sha256,
                core.dynamic_seam_bundle_sha256,
                core.motion_instance_v2_sha256,
                core.reviewed_motion_bundle_sha256,
                admission.sha256, admission.canonical_bytes.decode("utf-8"),
                core._motion_json, receipt,
            )
        except MotionInstanceV3PreparedV2Error:
            raise
        except (
            AttributeError, BodySwayMotionConsumerAdmissionV2Error, KeyError,
            OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
        ) as exc:
            raise MotionInstanceV3PreparedV2Error(
                f"MotionInstance v3 v2 source seal failed: {exc}"
            ) from exc

    def replay_motion_instance_v3_prepared_v2(
        admission: Mapping[str, Any],
        dynamic_bundle: VerifiedBodySwayDynamicSeamBundleV2,
        reviewed_bundle: VerifiedReviewedMotionBundle,
    ) -> PreparedMotionInstanceV3V2:
        """Replay historical admission without observing current heads."""

        try:
            root = bounded_body_sway_admission_v2(admission)
            core = compile_motion_instance_v3_prepared_core_v2(
                dynamic_bundle, reviewed_bundle,
            )
            before, after = body_sway_admission_observations_v2(
                core._consumer_core, root,
            )
            return seal_motion_instance_v3_prepared_v2(
                core, before, after, expected_admission=root,
            )
        except MotionInstanceV3PreparedV2Error:
            raise
        except (
            AttributeError, BodySwayMotionConsumerAdmissionV2Error, KeyError,
            OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
        ) as exc:
            raise MotionInstanceV3PreparedV2Error(
                f"Historical P10.6a v2 replay failed: {exc}"
            ) from exc

    return (
        MotionInstanceV3PreparedCoreV2, PreparedMotionInstanceV3V2,
        compile_motion_instance_v3_prepared_core_v2,
        seal_motion_instance_v3_prepared_v2,
        replay_motion_instance_v3_prepared_v2,
    )
(
    MotionInstanceV3PreparedCoreV2,
    PreparedMotionInstanceV3V2,
    compile_motion_instance_v3_prepared_core_v2,
    seal_motion_instance_v3_prepared_v2,
    replay_motion_instance_v3_prepared_v2,
) = _build_prepared_api()
del _build_prepared_api


__all__ = [
    "MotionInstanceV3PreparedCoreV2", "MotionInstanceV3PreparedV2Error",
    "PreparedMotionInstanceV3V2",
    "compile_motion_instance_v3_prepared_core_v2",
    "replay_motion_instance_v3_prepared_v2",
    "seal_motion_instance_v3_prepared_v2",
]
