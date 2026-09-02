"""Read-only exact P10.7a v2 to P10.7b v2 source bridge."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
import json
from pathlib import Path
from typing import Any

from .spine42_v3_bundle_reader_v2 import (
    VerifiedSpine42V3BundleReaderV2,
    VerifiedSpine42V3BundleReaderV2Error,
    VerifiedSpine42V3BundleV2,
)
from .spine42_v3_runtime_plan_v2 import (
    build_spine42_v3_runtime_plan_v2,
    canonical_spine42_v3_runtime_plan_bytes_v2,
    require_spine42_v3_runtime_plan_v2,
)
from .spine42_v3_runtime_source_admission_v2 import (
    build_spine42_v3_runtime_source_admission_v2,
    canonical_spine42_v3_runtime_source_admission_bytes_v2,
    require_spine42_v3_runtime_source_admission_v2,
)


class Spine42V3RuntimeSourceBridgeV2Error(RuntimeError):
    """Fixed path-free failure boundary for P10.7b v2 source replay."""


def _issued_types():
    receipt = object()

    @dataclass(frozen=True, slots=True)
    class VerifiedSpine42V3RuntimeSourceV2:
        project_id: str
        clip_id: str
        skeleton_json_sha256: str
        spine42_v3_bundle_sha256: str
        source_contract_sha256: str
        profile_sha256: str
        capture_plan_sha256: str
        admission_sha256: str
        _plan_bytes: bytes = field(repr=False)
        _admission_bytes: bytes = field(repr=False)
        _verification_receipt: InitVar[object] = None

        def __post_init__(self, _verification_receipt: object) -> None:
            if _verification_receipt is not receipt:
                raise Spine42V3RuntimeSourceBridgeV2Error(
                    "Verified runtime source v2 values are bridge-issued only"
                )

        @property
        def plan(self) -> dict[str, Any]:
            return json.loads(self._plan_bytes)

        @property
        def admission(self) -> dict[str, Any]:
            return json.loads(self._admission_bytes)

        @property
        def document_bytes(self) -> dict[str, bytes]:
            return {
                "official-runtime-capture-plan-v2.json": self._plan_bytes,
                "official-runtime-source-admission-v2.json": (
                    self._admission_bytes
                ),
            }

    @dataclass(frozen=True, slots=True)
    class VerifiedSpine42V3RuntimeSourceBridgeV2:
        state_root: Path

        def __post_init__(self) -> None:
            object.__setattr__(self, "state_root", Path(self.state_root))

        def build(
            self,
            project_id: str,
            skeleton_json_sha256: str,
            bundle_sha256: str,
        ) -> VerifiedSpine42V3RuntimeSourceV2:
            """Exact-read one explicit v2 address and emit planning authority."""

            try:
                bundle = VerifiedSpine42V3BundleReaderV2(
                    self.state_root
                ).load(project_id, skeleton_json_sha256, bundle_sha256)
                return self.build_from_verified(bundle)
            except Spine42V3RuntimeSourceBridgeV2Error:
                raise
            except _FAILURES as exc:
                raise Spine42V3RuntimeSourceBridgeV2Error(
                    "P10.7b v2 runtime source build failed"
                ) from exc

        def build_from_verified(
            self,
            bundle: VerifiedSpine42V3BundleV2,
        ) -> VerifiedSpine42V3RuntimeSourceV2:
            """Build from the same reader-issued in-memory P10.7a v2 value."""

            try:
                if type(bundle) is not VerifiedSpine42V3BundleV2:
                    raise Spine42V3RuntimeSourceBridgeV2Error(
                        "P10.7b v2 requires a reader-issued P10.7a v2 bundle"
                    )
                plan = build_spine42_v3_runtime_plan_v2(bundle)
                admission = build_spine42_v3_runtime_source_admission_v2(
                    bundle, plan,
                )
                exact_plan = require_spine42_v3_runtime_plan_v2(
                    plan, bundle=bundle,
                )
                exact_admission = (
                    require_spine42_v3_runtime_source_admission_v2(
                        admission, bundle=bundle, plan=exact_plan,
                    )
                )
                return VerifiedSpine42V3RuntimeSourceV2(
                    bundle.project_id, bundle.clip_id,
                    bundle.skeleton_json_sha256, bundle.bundle_sha256,
                    exact_admission["source_contract_sha256"],
                    exact_admission["profile_sha256"],
                    exact_plan["capture_plan_sha256"],
                    exact_admission["admission_sha256"],
                    canonical_spine42_v3_runtime_plan_bytes_v2(exact_plan),
                    canonical_spine42_v3_runtime_source_admission_bytes_v2(
                        exact_admission
                    ),
                    receipt,
                )
            except Spine42V3RuntimeSourceBridgeV2Error:
                raise
            except _FAILURES as exc:
                raise Spine42V3RuntimeSourceBridgeV2Error(
                    "P10.7b v2 runtime source build failed"
                ) from exc

        def rebuild_and_verify(
            self,
            expected: VerifiedSpine42V3RuntimeSourceV2,
        ) -> VerifiedSpine42V3RuntimeSourceV2:
            """Historical exact replay from the source's explicit v2 address."""

            if type(expected) is not VerifiedSpine42V3RuntimeSourceV2:
                raise Spine42V3RuntimeSourceBridgeV2Error(
                    "Expected runtime source v2 value is not bridge-issued"
                )
            rebuilt = self.build(
                expected.project_id, expected.skeleton_json_sha256,
                expected.spine42_v3_bundle_sha256,
            )
            if _identity(rebuilt) != _identity(expected) \
                    or rebuilt.document_bytes != expected.document_bytes:
                raise Spine42V3RuntimeSourceBridgeV2Error(
                    "Runtime source v2 differs from exact historical replay"
                )
            return rebuilt

    return VerifiedSpine42V3RuntimeSourceV2, VerifiedSpine42V3RuntimeSourceBridgeV2


def _identity(value) -> tuple[str, ...]:
    return (
        value.project_id, value.clip_id, value.skeleton_json_sha256,
        value.spine42_v3_bundle_sha256, value.source_contract_sha256,
        value.profile_sha256, value.capture_plan_sha256,
        value.admission_sha256,
    )


(
    VerifiedSpine42V3RuntimeSourceV2,
    VerifiedSpine42V3RuntimeSourceBridgeV2,
) = _issued_types()


_FAILURES = (
    AttributeError, KeyError, OSError, OverflowError, RecursionError,
    RuntimeError, TypeError, UnicodeError, ValueError,
    VerifiedSpine42V3BundleReaderV2Error,
)


__all__ = [
    "Spine42V3RuntimeSourceBridgeV2Error",
    "VerifiedSpine42V3RuntimeSourceBridgeV2",
    "VerifiedSpine42V3RuntimeSourceV2",
]
