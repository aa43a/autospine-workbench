"""Loopback HTTP adapter for one exact region rebind adoption."""

from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable

from .contracts import ContractValidationError
from .current_project_chain import (
    CurrentProjectChainChangedError,
    CurrentProjectChainError,
)
from .http_json_request import (
    HttpJsonRequestError,
    drain_bounded_request_body,
    read_json_object_request,
)
from .project_errors import ProjectNotFoundError, RevisionConflictError
from .project_store import ProjectStore, ProjectStoreError
from .region_rebind_adoption import (
    RegionRebindAdoptionApplication,
    RegionRebindAdoptionBindingChanged,
    RegionRebindAdoptionError,
    RegionRebindAdoptionHeadChanged,
    RegionRebindAdoptionHistorical,
    RegionRebindAdoptionNotFound,
    RegionRebindAdoptionUnavailable,
)
from .region_rebind_adoption_http_security import (
    RegionRebindAdoptionHttpSecurityError,
    require_region_rebind_adoption_headers,
)


MAX_REQUEST_BYTES = 2 * 1024 * 1024
ALLOW_METHODS = "POST, OPTIONS"
SendJson = Callable[[int, Any], None]


def is_region_rebind_adoption_path(parts: list[str]) -> bool:
    return len(parts) == 6 \
        and parts[:3] == ["api", "idle-behavior", "structural-probes"] \
        and parts[4] == "rebind-adoptions"


def dispatch_region_rebind_adoption_post(
    parts: list[str], handler: Any, store: ProjectStore, send_json: SendJson,
) -> bool:
    """Verify and commit one explicit recommendation with no path inputs."""

    if not is_region_rebind_adoption_path(parts):
        return False
    try:
        require_region_rebind_adoption_headers(handler.headers)
        request = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        receipt = RegionRebindAdoptionApplication(store).adopt(
            parts[3], parts[5], request,
        )
        send_json(HTTPStatus.OK, receipt)
    except RegionRebindAdoptionHttpSecurityError as exc:
        drain_bounded_request_body(handler, maximum_bytes=MAX_REQUEST_BYTES)
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except RegionRebindAdoptionNotFound:
        send_json(HTTPStatus.NOT_FOUND, {
            "error": "region_rebind_adoption_not_found",
            "message": "The exact region rebind recommendation is unavailable.",
        })
    except RegionRebindAdoptionHistorical:
        send_json(HTTPStatus.CONFLICT, {
            "error": "region_rebind_adoption_historical_read_only",
            "message": "Historical structural-probe packages are read-only.",
        })
    except RegionRebindAdoptionBindingChanged:
        send_json(HTTPStatus.CONFLICT, {
            "error": "region_rebind_binding_changed",
            "message": "The layer binding changed; rerun P10.2 before adopting.",
        })
    except RevisionConflictError as exc:
        send_json(HTTPStatus.CONFLICT, exc.as_dict())
    except (RegionRebindAdoptionError, ContractValidationError):
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_region_rebind_adoption_request",
            "message": "The region rebind adoption request is invalid.",
        })
    except CurrentProjectChainChangedError:
        send_json(HTTPStatus.CONFLICT, {
            "error": "region_rebind_project_chain_changed",
            "message": "The project changed; reload before adopting.",
        })
    except RegionRebindAdoptionHeadChanged:
        send_json(HTTPStatus.CONFLICT, {
            "error": "region_rebind_p10_head_changed",
            "message": "P10.1 changed; reload P10.2 before adopting.",
        })
    except RegionRebindAdoptionUnavailable:
        send_json(HTTPStatus.CONFLICT, {
            "error": "region_rebind_adoption_unavailable",
            "message": "The exact region rebind recommendation could not be adopted.",
        })
    except ProjectNotFoundError:
        send_json(HTTPStatus.NOT_FOUND, {
            "error": "project_not_found", "message": "Project not found.",
        })
    except (CurrentProjectChainError, ProjectStoreError):
        send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
            "error": "region_rebind_project_chain_unavailable",
            "message": "The current project chain could not be inspected.",
        })
    return True


def send_region_rebind_adoption_method_not_allowed(handler: Any) -> None:
    body = json.dumps({
        "error": "method_not_allowed", "message": "Method not allowed.",
    }, separators=(",", ":")).encode("utf-8")
    handler._send_bytes(  # noqa: SLF001 - route adapter uses handler primitive
        HTTPStatus.METHOD_NOT_ALLOWED,
        body,
        "application/json; charset=utf-8",
        extra_headers={"Allow": ALLOW_METHODS},
        visual_review=True,
    )
