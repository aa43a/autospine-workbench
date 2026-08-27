"""Immutable official-runtime sessions for exact P10.7a Spine bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
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

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def plan(self) -> dict[str, Any]:
        return self.document["plan"]

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return tuple(self.document["artifact_ids"])

    def session(self, artifact_id: str) -> dict[str, Any]:
        document = self.document
        artifact = next((row for row in document["plan"]["artifacts"]
                         if row["artifact_id"] == artifact_id), None)
        if artifact is None:
            raise Spine42V3RuntimeSessionError(
                "Artifact is absent from the exact runtime plan"
            )
        case = next((row for row in document["plan"]["cases"]
                     if row["case_id"] == artifact["case_id"]), None)
        if case is None:
            raise Spine42V3RuntimeSessionError(
                "Artifact case is absent from the exact runtime plan"
            )
        return _copy({
            "format": SESSION_FORMAT,
            "format_version": FORMAT_VERSION,
            "session_set_sha256": self.sha256,
            "plan_sha256": document["plan_sha256"],
            "source": document["source"],
            "runtime": document["runtime"],
            "assets": document["assets"],
            "capture": document["plan"]["capture"],
            "case": case,
            "artifact": artifact,
            "expected_observables": _artifact_observables(
                document["runtime_inventory"], artifact
            ),
        })


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
        raw = bundle.document_bytes
        assets = {
            "skeleton_sha256": _sha(raw["skeleton.json"]),
            "atlas_sha256": _sha(raw["skeleton.atlas"]),
            "texture_sha256": _sha(raw["skeleton.png"]),
        }
        if tuple(assets.values()) != (
            bundle.skeleton_json_sha256, bundle.atlas_sha256,
            bundle.png_sha256,
        ):
            raise Spine42V3RuntimeSessionError(
                "Bundle asset bytes differ from their verified identities"
            )
        artifacts = expected_plan["artifacts"]
        artifact_ids = [row["artifact_id"] for row in artifacts]
        if len(artifact_ids) != len(set(artifact_ids)) or not artifact_ids:
            raise Spine42V3RuntimeSessionError(
                "Runtime plan artifact inventory is empty or duplicated"
            )
        value = {
            "format": SESSION_SET_FORMAT,
            "format_version": FORMAT_VERSION,
            "source": expected_plan["source"],
            "runtime": expected_plan["runtime"],
            "assets": assets,
            "plan_sha256": spine42_v3_runtime_plan_sha256(expected_plan),
            "plan": expected_plan,
            "artifact_ids": artifact_ids,
            "runtime_inventory": _runtime_inventory(bundle),
            "summary": {
                "case_count": len(expected_plan["cases"]),
                "artifact_count": len(artifact_ids),
            },
        }
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
    js, css = runtime.javascript_bytes, runtime.stylesheet_bytes
    if type(js) is not bytes or not 0 < len(js) <= MAX_RUNTIME_JAVASCRIPT_BYTES \
            or type(css) is not bytes \
            or not 0 < len(css) <= MAX_RUNTIME_STYLESHEET_BYTES:
        raise Spine42V3RuntimeSessionError(
            "Official runtime byte snapshots are invalid"
        )
    expected = (
        SPINE_PLAYER_JAVASCRIPT_SHA256,
        SPINE_PLAYER_STYLESHEET_SHA256,
    )
    actual = runtime.javascript_sha256, runtime.stylesheet_sha256
    content = _sha(js), _sha(css)
    declared = (
        plan["runtime"]["javascript_sha256"],
        plan["runtime"]["stylesheet_sha256"],
    )
    if actual != expected or content != expected or declared != expected:
        raise Spine42V3RuntimeSessionError(
            "Official runtime bytes differ from the pinned capture profile"
        )


def _require_capture_profile(plan) -> None:
    capture = plan["capture"]
    if capture["viewport"] != {"width": 640, "height": 640} \
            or capture["device_pixel_ratio"] != 1 \
            or capture["preserve_drawing_buffer"] is not True:
        raise Spine42V3RuntimeSessionError(
            "Runtime plan does not use the fixed 640x640 DPR1 profile"
        )


def _require_harness(plan) -> None:
    expected = CAPTURE_JS_SHA256, CAPTURE_CSS_SHA256
    actual = _sha(CAPTURE_JS), _sha(CAPTURE_CSS)
    declared = (
        plan["harness"]["javascript_sha256"],
        plan["harness"]["stylesheet_sha256"],
    )
    if actual != expected or declared != expected:
        raise Spine42V3RuntimeSessionError(
            "Runtime capture harness differs from the pinned profile"
        )


def _runtime_inventory(bundle) -> dict[str, Any]:
    skeleton = bundle.skeleton_json
    slots = skeleton["slots"]
    return {
        "clip_ids": list(skeleton["animations"]),
        "slot_ids": [row["name"] for row in slots],
        "attachments": [
            {"slot_id": row["name"], "attachment_id": row["attachment"]}
            for row in slots if row.get("attachment") is not None
        ],
    }


def _artifact_observables(inventory, artifact) -> dict[str, Any]:
    slots = inventory["slot_ids"]
    isolated = artifact["kind"] == "attachment_isolate"
    visible = [artifact["slot_id"]] if isolated else list(slots)
    return {
        "official_runtime_loaded": True,
        **inventory,
        "isolation": {
            "artifact_kind": artifact["kind"],
            "visible_slot_ids": visible,
            "hidden_slot_ids": [slot for slot in slots if slot not in visible],
        },
    }


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _copy(value: Any) -> dict[str, Any]:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


__all__ = [
    "Spine42V3RuntimeSessionError", "Spine42V3RuntimeSessions",
    "build_spine42_v3_runtime_sessions",
    "require_exact_spine42_v3_runtime_sessions",
]
