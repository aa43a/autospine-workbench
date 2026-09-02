"""Version-neutral pure helpers for immutable Spine runtime sessions."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


def copy_json(value: Any) -> Any:
    return json.loads(canonical_json(value))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_session_set_value(
    *, session_set_format: str, format_version: int, source: dict,
    runtime: dict, assets: dict, plan_sha256: str, plan: dict,
    artifact_ids: list[str], runtime_inventory: dict,
    source_admission: dict | None = None,
) -> dict[str, Any]:
    value = {
        "format": session_set_format,
        "format_version": format_version,
        "source": source,
        "runtime": runtime,
        "assets": assets,
        "plan_sha256": plan_sha256,
        "plan": plan,
        "artifact_ids": artifact_ids,
        "runtime_inventory": runtime_inventory,
        "summary": {
            "case_count": len(plan["cases"]),
            "artifact_count": len(artifact_ids),
        },
    }
    if source_admission is not None:
        value["source_admission_sha256"] = source_admission[
            "admission_sha256"
        ]
        value["source_admission"] = source_admission
    return value


def build_session_projection(
    canonical: str, *, session_format: str, format_version: int,
    error_type: type[ValueError],
) -> tuple[tuple[str, ...], bytes, tuple[tuple[str, bytes], ...], bytes | None]:
    """Parse and index a session set once, then project every artifact."""

    try:
        if type(canonical) is not str:
            raise error_type("Runtime session set must be canonical JSON text")
        document = json.loads(canonical)
        if type(document) is not dict or type(document.get("plan")) is not dict:
            raise error_type("Runtime session set document is invalid")
        plan = document["plan"]
        artifacts = _unique_index(
            plan.get("artifacts"), "artifact_id", "artifact", error_type,
        )
        cases = _unique_index(
            plan.get("cases"), "case_id", "case", error_type,
        )
        supplied = document.get("artifact_ids")
        artifact_ids = tuple(supplied) if type(supplied) is list else ()
        if not artifact_ids or artifact_ids != tuple(artifacts) \
                or any(type(item) is not str for item in artifact_ids):
            raise error_type("Runtime session artifact inventory is invalid")
        session_set_sha256 = sha256_bytes(canonical.encode("utf-8"))
        items = []
        for artifact_id in artifact_ids:
            artifact = artifacts[artifact_id]
            case = cases.get(artifact.get("case_id"))
            if case is None:
                raise error_type(
                    "Artifact case is absent from the exact runtime plan"
                )
            value = _artifact_session_value(
                document, artifact, case, session_format=session_format,
                format_version=format_version,
                session_set_sha256=session_set_sha256,
            )
            items.append((artifact_id, canonical_json(value).encode("utf-8")))
        admission = document.get("source_admission")
        admission_bytes = (
            canonical_json(admission).encode("utf-8")
            if admission is not None else None
        )
        return (
            artifact_ids, canonical_json(plan).encode("utf-8"),
            tuple(items), admission_bytes,
        )
    except error_type:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise error_type("Runtime session set cannot be indexed") from exc


def _artifact_session_value(
    document, artifact, case, *, session_format, format_version,
    session_set_sha256,
):
    value = {
        "format": session_format,
        "format_version": format_version,
        "session_set_sha256": session_set_sha256,
        "plan_sha256": document["plan_sha256"],
        "source": document["source"],
        "runtime": document["runtime"],
        "assets": document["assets"],
        "capture": document["plan"]["capture"],
        "case": case,
        "artifact": artifact,
        "expected_observables": artifact_observables(
            document["runtime_inventory"], artifact,
        ),
    }
    if "source_admission_sha256" in document:
        value["source_admission_sha256"] = document[
            "source_admission_sha256"
        ]
    return value


def _unique_index(rows, key, label, error_type):
    if type(rows) is not list:
        raise error_type(f"Runtime session {label} inventory is invalid")
    result = {}
    for row in rows:
        identity = row.get(key) if type(row) is dict else None
        if type(identity) is not str or not identity or identity in result:
            raise error_type(f"Runtime session {label} inventory is invalid")
        result[identity] = row
    return result


def require_runtime_snapshot(
    runtime, plan, *, expected_javascript_sha256: str,
    expected_stylesheet_sha256: str, max_javascript_bytes: int,
    max_stylesheet_bytes: int, error_type: type[ValueError],
) -> None:
    javascript = runtime.javascript_bytes
    stylesheet = runtime.stylesheet_bytes
    if type(javascript) is not bytes \
            or not 0 < len(javascript) <= max_javascript_bytes \
            or type(stylesheet) is not bytes \
            or not 0 < len(stylesheet) <= max_stylesheet_bytes:
        raise error_type("Official runtime byte snapshots are invalid")
    expected = expected_javascript_sha256, expected_stylesheet_sha256
    actual = runtime.javascript_sha256, runtime.stylesheet_sha256
    content = sha256_bytes(javascript), sha256_bytes(stylesheet)
    declared = (
        plan["runtime"]["javascript_sha256"],
        plan["runtime"]["stylesheet_sha256"],
    )
    if actual != expected or content != expected or declared != expected:
        raise error_type(
            "Official runtime bytes differ from the pinned capture profile"
        )


def require_harness_snapshot(
    plan, javascript: bytes, stylesheet: bytes, *,
    javascript_sha256: str, stylesheet_sha256: str,
    error_type: type[ValueError],
) -> None:
    expected = javascript_sha256, stylesheet_sha256
    actual = sha256_bytes(javascript), sha256_bytes(stylesheet)
    declared = (
        plan["harness"]["javascript_sha256"],
        plan["harness"]["stylesheet_sha256"],
    )
    if actual != expected or declared != expected:
        raise error_type(
            "Runtime capture harness differs from the pinned profile"
        )


def require_capture_profile(plan, *, error_type: type[ValueError]) -> None:
    capture = plan["capture"]
    if capture["viewport"] != {"width": 640, "height": 640} \
            or capture["device_pixel_ratio"] != 1 \
            or capture["preserve_drawing_buffer"] is not True:
        raise error_type(
            "Runtime plan does not use the fixed 640x640 DPR1 profile"
        )


def bundle_asset_identities(bundle, *, error_type: type[ValueError]):
    raw = bundle.document_bytes
    assets = {
        "skeleton_sha256": sha256_bytes(raw["skeleton.json"]),
        "atlas_sha256": sha256_bytes(raw["skeleton.atlas"]),
        "texture_sha256": sha256_bytes(raw["skeleton.png"]),
    }
    if tuple(assets.values()) != (
        bundle.skeleton_json_sha256, bundle.atlas_sha256, bundle.png_sha256,
    ):
        raise error_type(
            "Bundle asset bytes differ from their verified identities"
        )
    return assets


def require_artifact_ids(plan, *, error_type: type[ValueError]):
    artifact_ids = [row["artifact_id"] for row in plan["artifacts"]]
    if len(artifact_ids) != len(set(artifact_ids)) or not artifact_ids:
        raise error_type(
            "Runtime plan artifact inventory is empty or duplicated"
        )
    return artifact_ids


def runtime_inventory(skeleton: dict[str, Any]) -> dict[str, Any]:
    slots = skeleton["slots"]
    return {
        "clip_ids": list(skeleton["animations"]),
        "slot_ids": [row["name"] for row in slots],
        "attachments": [
            {"slot_id": row["name"], "attachment_id": row["attachment"]}
            for row in slots if row.get("attachment") is not None
        ],
    }


def artifact_observables(inventory, artifact) -> dict[str, Any]:
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


__all__ = [
    "artifact_observables", "build_session_projection",
    "build_session_set_value",
    "bundle_asset_identities", "canonical_json", "copy_json",
    "require_artifact_ids",
    "require_capture_profile", "require_harness_snapshot",
    "require_runtime_snapshot", "runtime_inventory", "sha256_bytes",
]
