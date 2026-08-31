"""Current-chain, human-authorized adoption of one region rebind candidate."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .body_sway_probe_application import (
    BodySwayProbeApplication,
    BodySwayProbeApplicationError,
    BodySwayProbeApplicationHeadChanged,
    BodySwayProbeApplicationNotFound,
)
from .current_project_chain import (
    rebuild_current_project_chains,
    require_unchanged_current_project_chains,
)
from .idle_behavior_review_packages import (
    IdleBehaviorReviewPackageError,
    IdleBehaviorReviewPackageStale,
    require_current_idle_behavior_review_address,
)
from .idle_behavior_review_transaction import idle_behavior_review_transaction
from .project_errors import ProjectNotFoundError, RevisionConflictError
from .project_store import ProjectStore
from .region_rebind_adoption_request import (
    RegionRebindAdoptionRequestError,
    region_rebind_override_payload,
    require_region_rebind_adoption_request,
)
from .region_rebind_adoption_evidence import (
    RegionRebindAdoptionEvidenceError,
    RegionRebindLayerBindingChanged,
    RegionRebindLayerUnavailable,
    require_current_region_binding,
    require_idle_candidate_identity,
    require_live_region_rebind_relationship,
)
from .region_rebind_revision_provenance import (
    RegionRebindRevisionProvenanceError,
    build_region_rebind_revision_provenance,
    region_rebind_adoption_receipt,
)
from .region_rebind_validation import (
    RegionRebindValidationError,
    region_rebind_candidates_sha256,
)


class RegionRebindAdoptionError(ValueError):
    """Base class for a rejected adoption without state mutation."""

class RegionRebindAdoptionInvalid(RegionRebindAdoptionError):
    """The request does not name the exact server recommendation."""


class RegionRebindAdoptionNotFound(RegionRebindAdoptionError):
    """The package or candidate address cannot be resolved exactly."""

class RegionRebindAdoptionHistorical(RegionRebindAdoptionError):
    """The package is valid read-only history, but is not current."""


class RegionRebindAdoptionBindingChanged(RegionRebindAdoptionError):
    """The current effective layer binding no longer matches the source."""


class RegionRebindAdoptionUnavailable(RuntimeError):
    """Trusted exact evidence could not be verified for mutation."""


class RegionRebindAdoptionHeadChanged(RegionRebindAdoptionUnavailable):
    """The reviewed P10.1 head changed before the override CAS write."""


class RegionRebindAdoptionApplication:
    """Verify current evidence, then publish one provenance-bound CAS revision."""

    def __init__(self, store: ProjectStore) -> None:
        if not isinstance(store, ProjectStore):
            raise RegionRebindAdoptionUnavailable("Project store is invalid")
        self.store = store

    def adopt(
        self, package_id: str, candidate_sha256: str, payload: Any,
    ) -> dict[str, Any]:
        request = _request(package_id, candidate_sha256, payload)
        project_id = request["project_id"]
        try:
            project = self.store.get_project(project_id)
        except ProjectNotFoundError as exc:
            raise RegionRebindAdoptionNotFound("Project is unavailable") from exc
        _require_revision(project, request["base_revision"])
        _current_binding(project, request)

        project_ids = (project_id,)
        before = rebuild_current_project_chains(self.store, project_ids)
        try:
            address = require_current_idle_behavior_review_address(
                self.store.state_root, package_id,
                project_ids=project_ids, current_project_chains=before,
            )
        except IdleBehaviorReviewPackageStale as exc:
            raise RegionRebindAdoptionHistorical(
                "Historical structural-probe packages are read-only"
            ) from exc
        except IdleBehaviorReviewPackageError as exc:
            raise RegionRebindAdoptionNotFound(
                "Structural-probe package is unavailable"
            ) from exc
        if address.project_id != project_id:
            raise RegionRebindAdoptionInvalid("Package project differs")

        service = BodySwayProbeApplication(self.store.state_root)
        document, head, idle_candidate_sha256 = _prepare_candidate(
            service, package_id, project_ids, request, before[project_id],
        )
        project = self.store.get_project(project_id)
        _require_revision(project, request["base_revision"])
        _current_binding(project, request)
        try:
            require_live_region_rebind_relationship(
                project, document, request,
            )
        except RegionRebindAdoptionEvidenceError as exc:
            raise RegionRebindAdoptionUnavailable(str(exc)) from exc
        after = rebuild_current_project_chains(self.store, project_ids)
        require_unchanged_current_project_chains(before, after)
        with idle_behavior_review_transaction(
            self.store.state_root, idle_candidate_sha256,
        ):
            confirmed, confirmed_head, confirmed_candidate_sha256 = (
                _prepare_candidate(
                    service, package_id, project_ids, request,
                    after[project_id],
                )
            )
            if (confirmed, confirmed_head, confirmed_candidate_sha256) \
                    != (document, head, idle_candidate_sha256):
                raise RegionRebindAdoptionHeadChanged(
                    "P10.1 head changed before region rebind adoption"
                )
            provenance = _provenance(
                package_id, candidate_sha256, request, document,
                before[project_id], head,
            )
            saved = self.store.save_overrides(
                project_id, _override_payload(request),
                revision_provenance=provenance,
            )
            _require_saved(request, provenance, saved)
            return region_rebind_adoption_receipt(
                package_id=package_id,
                candidate_sha256=candidate_sha256,
                request=request,
                provenance=provenance,
                saved=saved,
            )


def _request(package_id, candidate_sha256, payload):
    try:
        return require_region_rebind_adoption_request(
            package_id, candidate_sha256, payload,
        )
    except RegionRebindAdoptionRequestError as exc:
        raise RegionRebindAdoptionInvalid(str(exc)) from exc


def _prepare_candidate(service, package_id, project_ids, request, chain):
    try:
        detail = service.prepare(package_id, project_ids=project_ids)
    except BodySwayProbeApplicationNotFound as exc:
        raise RegionRebindAdoptionNotFound(
            "Structural-probe package is unavailable"
        ) from exc
    except BodySwayProbeApplicationHeadChanged as exc:
        raise RegionRebindAdoptionHeadChanged(
            "P10.1 head changed before region rebind adoption"
        ) from exc
    except BodySwayProbeApplicationError as exc:
        raise RegionRebindAdoptionUnavailable(
            "Structural-probe evidence is unavailable"
        ) from exc
    return _candidate(detail, request, chain)


def _candidate(detail, request, chain):
    try:
        package = detail["package"]
        rows = detail["rebind_candidates"]
        report = detail["technical"]["report"]
        head = detail["history"]
        matches = [
            row for row in rows
            if row.get("candidate_sha256") == request["candidate_sha256"]
        ]
        if len(matches) != 1:
            raise RegionRebindAdoptionNotFound("Candidate is unavailable")
        document = matches[0]["document"]
        if region_rebind_candidates_sha256(document) \
                != request["candidate_sha256"]:
            raise RegionRebindAdoptionUnavailable("Candidate digest differs")
        source = document["source"]
        report_source = report["source"]
        p3, p9 = report_source["p3"], report_source["p9"]
        if package["project_id"] != request["project_id"] \
                or document["project_id"] != request["project_id"] \
                or source["rig_sha256"] != p3["rig_sha256"] \
                or source["motion_sha256"] != p9["motion_instance_v2_sha256"] \
                or source["motion_sample_count"] != report["schedule"]["sample_count"] \
                or p3["resolved_project_sha256"] != chain.resolved_project_sha256 \
                or p3["layer_manifest_sha256"] != chain.layer_manifest_sha256:
            raise RegionRebindAdoptionUnavailable("Candidate source chain differs")
        recommendation = document["recommendation"]
        if source["attachment_id"] != request["layer_id"] \
                or recommendation["status"] != "recommended" \
                or recommendation["authority"] != "none" \
                or recommendation["requires_explicit_review"] is not True \
                or recommendation["from_bone_id"] != request["from_bone_id"] \
                or recommendation["to_bone_id"] != request["to_bone_id"]:
            raise RegionRebindAdoptionInvalid(
                "Request differs from recommendation"
            )
        _require_head(head)
        idle_candidate_sha256 = require_idle_candidate_identity(detail, report)
        return document, deepcopy(dict(head)), idle_candidate_sha256
    except (RegionRebindAdoptionError, RegionRebindAdoptionUnavailable):
        raise
    except (KeyError, RegionRebindValidationError, TypeError, ValueError) as exc:
        raise RegionRebindAdoptionUnavailable(
            "Exact candidate evidence is invalid"
        ) from exc


def _require_revision(project, requested):
    current = project.get("overrides", {}).get("revision")
    if current != requested:
        raise RevisionConflictError(
            requested, current if type(current) is int else -1,
        )


def _current_binding(project, request):
    try:
        require_current_region_binding(project, request)
    except RegionRebindLayerBindingChanged as exc:
        raise RegionRebindAdoptionBindingChanged(str(exc)) from exc
    except RegionRebindLayerUnavailable as exc:
        raise RegionRebindAdoptionInvalid(str(exc)) from exc


def _provenance(package_id, candidate_sha, request, document, chain, head):
    try:
        return build_region_rebind_revision_provenance(
            package_id=package_id,
            candidate_sha256=candidate_sha,
            project_id=request["project_id"],
            revision=request["base_revision"] + 1,
            layer_id=request["layer_id"],
            from_bone_id=request["from_bone_id"],
            to_bone_id=request["to_bone_id"],
            source=document["source"],
            resolved_project_sha256=chain.resolved_project_sha256,
            layer_manifest_sha256=chain.layer_manifest_sha256,
            p10_head=head,
        )
    except RegionRebindRevisionProvenanceError as exc:
        raise RegionRebindAdoptionUnavailable(
            "Adoption provenance is invalid"
        ) from exc


def _override_payload(request):
    try:
        return region_rebind_override_payload(request)
    except RegionRebindAdoptionRequestError as exc:
        raise RegionRebindAdoptionInvalid(str(exc)) from exc


def _require_saved(request, provenance, saved):
    if saved.get("revision") != request["base_revision"] + 1 \
            or saved.get("revision_provenance") != provenance \
            or saved.get("layer_overrides", {}).get(
                request["layer_id"], {},
            ).get("candidate_bone") != request["to_bone_id"]:
        raise RegionRebindAdoptionUnavailable(
            "Saved override does not contain the adopted binding"
        )


def _require_head(value):
    if not isinstance(value, Mapping):
        raise RegionRebindAdoptionUnavailable("P10 head is invalid")
    required = {
        "current_revision", "head_decision_sha256", "action", "probe_status",
    }
    if set(value) != required:
        raise RegionRebindAdoptionUnavailable("P10 head fields are invalid")
