"""Read-only exceptions for the existing setup-region preview review gates."""
from copy import deepcopy
import re

from ..region_rig_contract import review_issues, validate_compile_inputs
from ..resolved_project import canonical_sha256
from .pipeline_profile import build_pipeline_profile

SCHEMA = "autospine.review-queue/v1"
SCOPE = "setup_region_preview"
INVALIDATION = ["layer_manifest", "region_rig", "spine_preview"]
ROLLBACK = "Restore the previous reviewed values in a new authoring revision."
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SOURCES = {"resolved_project_sha256", "layer_manifest_sha256", "input_identity_sha256"}
# reason: (type, risk, blocking, suggestion). No user-controlled prose is copied.
REASONS = {
    "semantic_review_required": ("semantic", "medium", True, "Confirm the layer role and character side."),
    "pivot_review_required": ("pivot", "medium", True, "Inspect the layer and confirm its pivot position."),
    "binding_review_required": ("binding", "high", True, "Choose and review a supported skeleton bone."),
    "layer_review_required": ("rig", "medium", True, "Review the layer disposition and QA flags."),
    "joint_review_required": ("joint", "high", True, "Inspect the joint evidence and confirm its position."),
    "joint_candidate_rejected": ("joint", "high", True, "Select another candidate or place the joint manually."),
    "joint_unobservable": ("joint", "low", False, "This joint was marked unobservable; revisit it if better evidence becomes available."),
    "split_review_required": ("split", "high", True, "Inspect the split children and accept or revise the split."),
    "split_candidate_rejected": ("split", "high", True, "Revise the rejected split before requesting a preview."),
    "split_decision_stale": ("split", "high", True, "Rebuild split evidence and review it against the current source."),
    "project_review_required": ("rig", "high", True, "Complete the remaining project review before requesting a preview."),
    "region_geometry_unsupported": ("rig", "high", True, "Correct the unsupported region geometry or layer configuration."),
    "certification_exact_entry_required": ("rig", "high", True, "Use the existing exact certification workflow."),
}


class ReviewQueueError(ValueError):
    def __init__(self, reason_code="review_queue_invalid"):
        self.reason_code = reason_code
        super().__init__(reason_code)


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ReviewQueueError()
    return value


def _item_id(kind, entity_id, reason):
    return "review-" + canonical_sha256({"type": kind, "entity_id": entity_id, "reason_code": reason})


def _evidence(project_id, layer_id=None):
    suffix = f"layers/{_identifier(layer_id)}/image" if layer_id else "composite"
    return [{"kind": "layer_image" if layer_id else "composite_image",
             "url": f"/api/projects/{project_id}/{suffix}"}]


def build_review_queue(snapshot, profile="production_review"):
    """Describe actual authoring gates without creating decisions or authority."""
    build_pipeline_profile(profile)
    project_id = _identifier(snapshot.project_id)
    try:
        sources = snapshot.source_addresses
        validate_compile_inputs(snapshot.manifest, snapshot.resolved, sources["layer_manifest_sha256"])
        if snapshot.resolved["sha256"] != sources["resolved_project_sha256"]:
            raise ReviewQueueError("review_queue_source_mismatch")
        issues = review_issues(snapshot.manifest, snapshot.resolved)
    except ReviewQueueError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise ReviewQueueError("review_queue_source_mismatch") from exc
    items = {}
    original_layers = {_identifier(row["id"]) for row in snapshot.resolved["layers"]}

    def add(reason, entity_id, layer_id=None):
        kind, risk, blocking, suggestion = REASONS[reason]
        entity_id = _identifier(entity_id)
        identifier = _item_id(kind, entity_id, reason)
        items[identifier] = {
            "id": identifier, "type": kind, "entity_id": entity_id,
            "risk": risk, "blocking": blocking, "reason_code": reason,
            "suggestion": suggestion, "evidence": _evidence(project_id, layer_id),
            "rollback": ROLLBACK, "invalidation": list(INVALIDATION),
        }

    for layer in snapshot.manifest["layers"]:
        layer_id = layer["layer_id"]
        parent_ids = layer.get("derivation", {}).get("parent_layer_ids", [])
        evidence_id = layer_id if layer_id in original_layers else next(
            (identifier for identifier in parent_ids if identifier in original_layers), None,
        )
        specific = False
        if layer["rig_hint"]["attachment_kind"] == "region":
            pivot = layer["rig_hint"].get("pivot")
            checks = (
                (layer["semantic"]["mapping_method"] != "manual", "semantic_review_required"),
                (not isinstance(pivot, dict) or pivot.get("method") != "manual", "pivot_review_required"),
                (layer["rig_hint"].get("candidate_bone") is None or
                 "BONE_BINDING_REVIEW_REQUIRED" in layer["qa"]["flags"], "binding_review_required"),
            )
            for missing, reason in checks:
                if missing:
                    specific = True
                    add(reason, layer_id, evidence_id)
        if layer["qa"]["status"] == "manual_required" and not specific:
            add("layer_review_required", layer_id, evidence_id)

    qa = snapshot.resolved["qa"]
    unresolved = set(qa["unresolved_joint_ids"])
    for joint in snapshot.resolved["skeleton"]["joints"]:
        state = joint["review_state"]
        if joint["id"] in unresolved:
            add("joint_candidate_rejected" if state == "candidate_rejected"
                else "joint_review_required", joint["id"])
        elif state == "unobservable":
            add("joint_unobservable", joint["id"])
    for key, reason in (
        ("unreviewed_split_layer_ids", "split_review_required"),
        ("rejected_split_layer_ids", "split_candidate_rejected"),
        ("stale_split_layer_ids", "split_decision_stale"),
    ):
        for layer_id in qa[key]:
            add(reason, layer_id, layer_id)
    if issues and not any(item["blocking"] for item in items.values()):
        add("project_review_required", project_id)
    if snapshot.region_compilation is None:
        add("region_geometry_unsupported", project_id)
    if profile == "certification_exact":
        add("certification_exact_entry_required", project_id)
    document = {
        "schema": SCHEMA, "scope": SCOPE, "authority": "none",
        "project_id": project_id, "profile": profile,
        "source_addresses": deepcopy(sources),
        "status": _status(list(items.values())),
        "items": sorted(items.values(), key=lambda row: row["id"]),
    }
    document["queue_sha256"] = canonical_sha256(document)
    return validate_review_queue(document)


def _status(items):
    if any(row["reason_code"] in {"region_geometry_unsupported", "certification_exact_entry_required"} for row in items):
        return "blocked"
    return "needs_review" if any(row["blocking"] for row in items) else "clear"


def validate_review_queue(document):
    """Validate closed enums, evidence routes, content identity and derivations."""
    try:
        _validate(document)
    except ReviewQueueError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise ReviewQueueError() from exc
    return deepcopy(document)


def _validate(document):
    if type(document) is not dict or set(document) != {
        "schema", "scope", "authority", "project_id", "profile",
        "source_addresses", "status", "items", "queue_sha256",
    } or document["schema"] != SCHEMA or document["scope"] != SCOPE or document["authority"] != "none":
        raise ReviewQueueError()
    project_id = _identifier(document["project_id"])
    build_pipeline_profile(document["profile"])
    sources = document["source_addresses"]
    if type(sources) is not dict or set(sources) != _SOURCES or any(
        not isinstance(value, str) or not _SHA.fullmatch(value) for value in sources.values()
    ):
        raise ReviewQueueError()
    items = document["items"]
    if type(items) is not list or len(items) > 65536:
        raise ReviewQueueError()
    for item in items:
        if type(item) is not dict or set(item) != {
            "id", "type", "entity_id", "risk", "blocking", "reason_code",
            "suggestion", "evidence", "rollback", "invalidation",
        }:
            raise ReviewQueueError()
        entity = _identifier(item["entity_id"])
        kind, risk, blocking, suggestion = REASONS[item["reason_code"]]
        if item["type"] != kind or item["risk"] != risk or type(item["blocking"]) is not bool \
                or item["blocking"] != blocking or item["suggestion"] != suggestion \
                or item["rollback"] != ROLLBACK or item["invalidation"] != INVALIDATION \
                or item["id"] != _item_id(kind, entity, item["reason_code"]):
            raise ReviewQueueError()
        evidence = item["evidence"]
        if type(evidence) is not list or len(evidence) > 1:
            raise ReviewQueueError()
        for entry in evidence:
            if type(entry) is not dict or set(entry) != {"kind", "url"}:
                raise ReviewQueueError()
            if entry["kind"] == "composite_image":
                expected = f"/api/projects/{project_id}/composite"
                if entry["url"] != expected:
                    raise ReviewQueueError()
            elif entry["kind"] == "layer_image":
                if not isinstance(entry["url"], str) or not re.fullmatch(
                    re.escape(f"/api/projects/{project_id}/layers/") + r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}/image", entry["url"],
                ):
                    raise ReviewQueueError()
            else:
                raise ReviewQueueError()
    ids = [row["id"] for row in items]
    if ids != sorted(set(ids)) or document["status"] != _status(items):
        raise ReviewQueueError()
    body = {key: value for key, value in document.items() if key != "queue_sha256"}
    if document["queue_sha256"] != canonical_sha256(body):
        raise ReviewQueueError("review_queue_hash_invalid")
