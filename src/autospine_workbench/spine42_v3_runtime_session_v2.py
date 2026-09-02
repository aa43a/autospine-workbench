"""Version-isolated immutable runtime sessions for P10.7a v2 bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Any

from .spine42_runtime_inputs import Spine42RuntimePackage
from .spine42_v3_bundle_reader_v2 import VerifiedSpine42V3BundleV2
from .spine42_v3_runtime_capture_page import (
    CAPTURE_CSS, CAPTURE_CSS_SHA256, CAPTURE_JS, CAPTURE_JS_SHA256,
)
from .spine42_v3_runtime_plan_v2 import (
    require_spine42_v3_runtime_plan_v2,
    spine42_v3_runtime_plan_sha256_v2,
)
from .spine42_v3_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)
from .spine42_v3_runtime_session import (
    MAX_RUNTIME_JAVASCRIPT_BYTES, MAX_RUNTIME_STYLESHEET_BYTES,
)
from .spine42_v3_runtime_session_core import (
    build_session_projection, build_session_set_value,
    bundle_asset_identities, canonical_json, require_artifact_ids,
    require_capture_profile, require_harness_snapshot,
    require_runtime_snapshot, runtime_inventory, sha256_bytes,
)
from .spine42_v3_runtime_source_admission_v2 import (
    require_spine42_v3_runtime_source_admission_v2,
)
from .spine42_v3_runtime_source_bridge_v2 import (
    VerifiedSpine42V3RuntimeSourceV2,
)


SESSION_SET_FORMAT = "autospine-spine42-v3-runtime-session-set"
SESSION_FORMAT = "autospine-spine42-v3-runtime-session"
FORMAT_VERSION = 2


class Spine42V3RuntimeSessionV2Error(ValueError):
    """Raised when v2 source, plan, runtime, or assets disagree."""


@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeSessionsV2:
    _canonical_json: str = field(repr=False)
    _plan_bytes: bytes = field(init=False, repr=False, compare=False)
    _admission_bytes: bytes = field(init=False, repr=False, compare=False)
    _artifact_ids: tuple[str, ...] = field(
        init=False, repr=False, compare=False,
    )
    _session_items: tuple[tuple[str, bytes], ...] = field(
        init=False, repr=False, compare=False,
    )
    _session_index: Any = field(init=False, repr=False, compare=False)
    _sha256: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        artifact_ids, plan, items, admission = build_session_projection(
            self._canonical_json, session_format=SESSION_FORMAT,
            format_version=FORMAT_VERSION,
            error_type=Spine42V3RuntimeSessionV2Error,
        )
        if admission is None:
            raise Spine42V3RuntimeSessionV2Error(
                "Runtime session set v2 has no source admission"
            )
        object.__setattr__(self, "_artifact_ids", artifact_ids)
        object.__setattr__(self, "_plan_bytes", plan)
        object.__setattr__(self, "_admission_bytes", admission)
        object.__setattr__(self, "_session_items", items)
        object.__setattr__(
            self, "_session_index", MappingProxyType(dict(items)),
        )
        object.__setattr__(
            self, "_sha256", sha256_bytes(self.canonical_bytes),
        )

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def plan(self) -> dict[str, Any]:
        return json.loads(self._plan_bytes)

    @property
    def source_admission(self) -> dict[str, Any]:
        return json.loads(self._admission_bytes)

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return self._artifact_ids

    @property
    def session_bytes(self) -> dict[str, bytes]:
        """Return detached immutable byte values in exact artifact order."""

        return dict(self._session_items)

    def session(self, artifact_id: str) -> dict[str, Any]:
        if type(artifact_id) is not str or artifact_id not in self._session_index:
            raise Spine42V3RuntimeSessionV2Error(
                "Artifact is absent from the exact runtime plan"
            )
        return json.loads(self._session_index[artifact_id])


def build_spine42_v3_runtime_sessions_v2(
    bundle: VerifiedSpine42V3BundleV2,
    runtime: Spine42RuntimePackage,
    source: VerifiedSpine42V3RuntimeSourceV2,
) -> Spine42V3RuntimeSessionsV2:
    """Bind bridge admission, plan, assets, and runtime byte snapshots."""

    try:
        if type(bundle) is not VerifiedSpine42V3BundleV2 \
                or type(runtime) is not Spine42RuntimePackage \
                or type(source) is not VerifiedSpine42V3RuntimeSourceV2:
            raise Spine42V3RuntimeSessionV2Error(
                "Runtime sessions v2 require exact v2 source snapshots"
            )
        plan = require_spine42_v3_runtime_plan_v2(
            source.plan, bundle=bundle,
        )
        admission = require_spine42_v3_runtime_source_admission_v2(
            source.admission, bundle=bundle, plan=plan,
        )
        _require_source(source, bundle, plan, admission)
        _require_runtime(runtime, plan)
        require_harness_snapshot(
            plan, CAPTURE_JS, CAPTURE_CSS,
            javascript_sha256=CAPTURE_JS_SHA256,
            stylesheet_sha256=CAPTURE_CSS_SHA256,
            error_type=Spine42V3RuntimeSessionV2Error,
        )
        require_capture_profile(
            plan, error_type=Spine42V3RuntimeSessionV2Error,
        )
        assets = bundle_asset_identities(
            bundle, error_type=Spine42V3RuntimeSessionV2Error,
        )
        artifact_ids = require_artifact_ids(
            plan, error_type=Spine42V3RuntimeSessionV2Error,
        )
        value = build_session_set_value(
            session_set_format=SESSION_SET_FORMAT,
            format_version=FORMAT_VERSION, source=plan["source"],
            runtime=plan["runtime"], assets=assets,
            plan_sha256=spine42_v3_runtime_plan_sha256_v2(plan), plan=plan,
            artifact_ids=artifact_ids,
            runtime_inventory=runtime_inventory(bundle.skeleton_json),
            source_admission=admission,
        )
        return Spine42V3RuntimeSessionsV2(canonical_json(value))
    except Spine42V3RuntimeSessionV2Error:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        RuntimeError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3RuntimeSessionV2Error(
            "Spine v3 runtime session construction v2 failed"
        ) from exc


def require_exact_spine42_v3_runtime_sessions_v2(
    bundle: VerifiedSpine42V3BundleV2,
    runtime: Spine42RuntimePackage,
    source: VerifiedSpine42V3RuntimeSourceV2,
    sessions: Spine42V3RuntimeSessionsV2,
) -> Spine42V3RuntimeSessionsV2:
    if type(sessions) is not Spine42V3RuntimeSessionsV2:
        raise Spine42V3RuntimeSessionV2Error(
            "Runtime session set v2 type is invalid"
        )
    expected = build_spine42_v3_runtime_sessions_v2(
        bundle, runtime, source,
    )
    if sessions.canonical_bytes != expected.canonical_bytes:
        raise Spine42V3RuntimeSessionV2Error(
            "Runtime session set v2 differs from exact input replay"
        )
    return expected


def _require_source(source, bundle, plan, admission):
    expected = (
        bundle.project_id, bundle.clip_id, bundle.skeleton_json_sha256,
        bundle.bundle_sha256, plan["source_contract_sha256"],
        plan["profile_sha256"], plan["capture_plan_sha256"],
        admission["admission_sha256"],
    )
    actual = (
        source.project_id, source.clip_id, source.skeleton_json_sha256,
        source.spine42_v3_bundle_sha256, source.source_contract_sha256,
        source.profile_sha256, source.capture_plan_sha256,
        source.admission_sha256,
    )
    if actual != expected:
        raise Spine42V3RuntimeSessionV2Error(
            "Runtime source v2 identity differs from exact replay"
        )


def _require_runtime(runtime, plan):
    require_runtime_snapshot(
        runtime, plan,
        expected_javascript_sha256=SPINE_PLAYER_JAVASCRIPT_SHA256,
        expected_stylesheet_sha256=SPINE_PLAYER_STYLESHEET_SHA256,
        max_javascript_bytes=MAX_RUNTIME_JAVASCRIPT_BYTES,
        max_stylesheet_bytes=MAX_RUNTIME_STYLESHEET_BYTES,
        error_type=Spine42V3RuntimeSessionV2Error,
    )


__all__ = [
    "Spine42V3RuntimeSessionV2Error", "Spine42V3RuntimeSessionsV2",
    "build_spine42_v3_runtime_sessions_v2",
    "require_exact_spine42_v3_runtime_sessions_v2",
]
