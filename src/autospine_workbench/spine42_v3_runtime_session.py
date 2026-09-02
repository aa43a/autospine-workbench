"""Immutable official-runtime sessions for exact P10.7a Spine bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Any

from .spine42_runtime_inputs import Spine42RuntimePackage
from .spine42_runtime_profile import (
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)
from .spine42_v3_runtime_capture_page import (
    CAPTURE_CSS, CAPTURE_CSS_SHA256, CAPTURE_JS, CAPTURE_JS_SHA256,
)
from .spine42_v3_bundle_integrity import (
    VerifiedSpine42V3Bundle,
    replay_verified_spine42_v3_bundle,
)
from .spine42_v3_runtime_plan import (
    build_spine42_v3_runtime_plan,
    canonical_spine42_v3_runtime_plan_bytes,
    spine42_v3_runtime_plan_sha256,
)
from .spine42_v3_runtime_session_core import (
    build_session_projection, build_session_set_value,
    bundle_asset_identities, canonical_json, copy_json, require_artifact_ids,
    require_capture_profile, require_harness_snapshot,
    require_runtime_snapshot, runtime_inventory, sha256_bytes,
)


SESSION_SET_FORMAT = "autospine-spine42-v3-runtime-session-set"
SESSION_FORMAT = "autospine-spine42-v3-runtime-session"
FORMAT_VERSION = 1
MAX_RUNTIME_JAVASCRIPT_BYTES = 2 * 1024 * 1024
MAX_RUNTIME_STYLESHEET_BYTES = 512 * 1024


class Spine42V3RuntimeSessionError(ValueError):
    """Raised when bundle, plan, and runtime snapshots do not agree."""


@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeSessions:
    """Frozen complete artifact inventory with detached JSON access."""

    _canonical_json: str = field(repr=False)
    _plan_bytes: bytes = field(init=False, repr=False, compare=False)
    _artifact_ids: tuple[str, ...] = field(
        init=False, repr=False, compare=False,
    )
    _session_items: tuple[tuple[str, bytes], ...] = field(
        init=False, repr=False, compare=False,
    )
    _session_index: Any = field(init=False, repr=False, compare=False)
    _sha256: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        artifact_ids, plan, items, _admission = build_session_projection(
            self._canonical_json, session_format=SESSION_FORMAT,
            format_version=FORMAT_VERSION,
            error_type=Spine42V3RuntimeSessionError,
        )
        object.__setattr__(self, "_artifact_ids", artifact_ids)
        object.__setattr__(self, "_plan_bytes", plan)
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
    def artifact_ids(self) -> tuple[str, ...]:
        return self._artifact_ids

    @property
    def session_bytes(self) -> dict[str, bytes]:
        """Return detached immutable byte values in exact artifact order."""

        return dict(self._session_items)

    def session(self, artifact_id: str) -> dict[str, Any]:
        if type(artifact_id) is not str or artifact_id not in self._session_index:
            raise Spine42V3RuntimeSessionError(
                "Artifact is absent from the exact runtime plan"
            )
        return json.loads(self._session_index[artifact_id])


def build_spine42_v3_runtime_sessions(
    bundle: VerifiedSpine42V3Bundle,
    runtime: Spine42RuntimePackage,
    plan: dict[str, Any],
) -> Spine42V3RuntimeSessions:
    """Bind exact verified inputs into a replayable browser session set."""

    try:
        if type(bundle) is not VerifiedSpine42V3Bundle \
                or type(runtime) is not Spine42RuntimePackage \
                or type(plan) is not dict:
            raise Spine42V3RuntimeSessionError(
                "Runtime sessions require exact bundle, runtime, and plan snapshots"
            )
        replay_verified_spine42_v3_bundle(bundle)
        expected_plan = build_spine42_v3_runtime_plan(bundle)
        if canonical_spine42_v3_runtime_plan_bytes(plan) != \
                canonical_spine42_v3_runtime_plan_bytes(expected_plan):
            raise Spine42V3RuntimeSessionError(
                "Runtime plan differs from exact bundle replay"
            )
        _require_runtime(runtime, expected_plan)
        _require_harness(expected_plan)
        _require_capture_profile(expected_plan)
        assets = bundle_asset_identities(
            bundle, error_type=Spine42V3RuntimeSessionError,
        )
        artifact_ids = require_artifact_ids(
            expected_plan, error_type=Spine42V3RuntimeSessionError,
        )
        value = build_session_set_value(
            session_set_format=SESSION_SET_FORMAT,
            format_version=FORMAT_VERSION,
            source=expected_plan["source"],
            runtime=expected_plan["runtime"], assets=assets,
            plan_sha256=spine42_v3_runtime_plan_sha256(expected_plan),
            plan=expected_plan, artifact_ids=artifact_ids,
            runtime_inventory=runtime_inventory(bundle.skeleton_json),
        )
        return Spine42V3RuntimeSessions(_canonical(value))
    except Spine42V3RuntimeSessionError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3RuntimeSessionError(
            f"Spine v3 runtime session construction failed: {exc}"
        ) from exc


def require_exact_spine42_v3_runtime_sessions(
    bundle: VerifiedSpine42V3Bundle,
    runtime: Spine42RuntimePackage,
    sessions: Spine42V3RuntimeSessions,
) -> Spine42V3RuntimeSessions:
    """Rebuild all session bytes and reject cross-wired inputs."""

    if type(sessions) is not Spine42V3RuntimeSessions:
        raise Spine42V3RuntimeSessionError(
            "Runtime session set type is invalid"
        )
    expected = build_spine42_v3_runtime_sessions(
        bundle, runtime, sessions.plan
    )
    if sessions.canonical_bytes != expected.canonical_bytes:
        raise Spine42V3RuntimeSessionError(
            "Runtime session set differs from exact input replay"
        )
    return expected


def _require_runtime(runtime, plan) -> None:
    require_runtime_snapshot(
        runtime, plan,
        expected_javascript_sha256=SPINE_PLAYER_JAVASCRIPT_SHA256,
        expected_stylesheet_sha256=SPINE_PLAYER_STYLESHEET_SHA256,
        max_javascript_bytes=MAX_RUNTIME_JAVASCRIPT_BYTES,
        max_stylesheet_bytes=MAX_RUNTIME_STYLESHEET_BYTES,
        error_type=Spine42V3RuntimeSessionError,
    )


def _require_capture_profile(plan) -> None:
    require_capture_profile(plan, error_type=Spine42V3RuntimeSessionError)


def _require_harness(plan) -> None:
    require_harness_snapshot(
        plan, CAPTURE_JS, CAPTURE_CSS,
        javascript_sha256=CAPTURE_JS_SHA256,
        stylesheet_sha256=CAPTURE_CSS_SHA256,
        error_type=Spine42V3RuntimeSessionError,
    )


def _runtime_inventory(bundle) -> dict[str, Any]:
    return runtime_inventory(bundle.skeleton_json)


def _artifact_observables(inventory, artifact) -> dict[str, Any]:
    from .spine42_v3_runtime_session_core import artifact_observables
    return artifact_observables(inventory, artifact)


def _sha(value: bytes) -> str:
    return sha256_bytes(value)


def _copy(value: Any) -> dict[str, Any]:
    return copy_json(value)


def _canonical(value: Any) -> str:
    return canonical_json(value)


__all__ = [
    "Spine42V3RuntimeSessionError", "Spine42V3RuntimeSessions",
    "build_spine42_v3_runtime_sessions",
    "require_exact_spine42_v3_runtime_sessions",
]
