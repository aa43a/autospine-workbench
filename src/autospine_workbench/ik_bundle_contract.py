"""Canonical contract and domain-separated address for immutable P4 bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .ik_probe_report import IkProbeReportError, require_ik_probe_report
from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .ik_target_profile_validation import (
    IkTargetProfileValidationError,
    require_ik_target_profile,
)
from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256


BUNDLE_ADDRESS_DOMAIN = "autospine-ik-target-bundle-address/v1"
DOCUMENT_NAMES = ("profile.json", "probes.json")
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_DOCUMENT_BYTES = 16 * 1024 * 1024


class IkBundleContractError(ValueError):
    """Raised when proposed P4 bundle content is not strict and cross-bound."""


@dataclass(frozen=True, slots=True)
class IkBundleContract:
    """Frozen canonical bytes and their exact P4 content address."""

    project_id: str
    profile_sha256: str
    probes_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)


def build_ik_bundle_contract(
    project_id: str,
    profile: Mapping[str, Any],
    probes: Mapping[str, Any],
) -> IkBundleContract:
    """Validate, cross-bind, canonicalize, and address two P4 documents."""

    try:
        project = require_safe_token(project_id, "Project id")
        require_ik_target_profile(profile)
        require_ik_probe_report(probes, profile=profile)
        if profile.get("project_id") != project or probes.get("project_id") != project:
            raise IkBundleContractError("IK bundle project binding is invalid")
        profile_source = _source(profile.get("source"), "IK profile source")
        probe_source = _object(probes.get("source"), "IK probes source")
        _exact(
            probe_source,
            set(SOURCE_IDENTITY_FIELDS) | {"profile_sha256"},
            "IK probes source",
        )
        for field, digest in profile_source.items():
            if probe_source.get(field) != digest:
                raise IkBundleContractError("IK bundle P3 identity binding is invalid")
        profile_bytes = _document(profile, "profile.json")
        probes_bytes = _document(probes, "probes.json")
        if len(profile_bytes) + len(probes_bytes) > MAX_TOTAL_DOCUMENT_BYTES:
            raise IkBundleContractError("IK bundle JSON resource limit exceeded")
        profile_sha = _sha(profile_bytes)
        probes_sha = _sha(probes_bytes)
        if probe_source.get("profile_sha256") != profile_sha:
            raise IkBundleContractError("IK probes profile SHA binding is invalid")
        bundle_sha = ik_bundle_address_sha256(
            project, profile_sha, probes_sha, profile_source
        )
        return IkBundleContract(
            project, profile_sha, probes_sha, bundle_sha,
            ((DOCUMENT_NAMES[0], profile_bytes), (DOCUMENT_NAMES[1], probes_bytes)),
        )
    except IkBundleContractError:
        raise
    except (
        IkProbeReportError,
        IkTargetProfileValidationError,
        LayerManifestError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise IkBundleContractError(f"IK bundle contract failed: {exc}") from exc


def ik_bundle_address_sha256(
    project_id: str,
    profile_sha256: str,
    probes_sha256: str,
    source_identities: Mapping[str, str],
) -> str:
    """Return the domain-separated address for one exact profile/report pair."""

    try:
        project = require_safe_token(project_id, "Project id")
        profile_sha = require_sha256(profile_sha256, "IK profile")
        probes_sha = require_sha256(probes_sha256, "IK probes")
        source = _source(source_identities, "IK bundle source identities")
        payload = {
            "domain": BUNDLE_ADDRESS_DOMAIN,
            "project_id": project,
            "profile_sha256": profile_sha,
            "probes_sha256": probes_sha,
            "source": source,
        }
        return _sha(_canonical(payload))
    except IkBundleContractError:
        raise
    except (LayerManifestError, TypeError, ValueError) as exc:
        raise IkBundleContractError("IK bundle address inputs are invalid") from exc


def _source(value: Any, label: str) -> dict[str, str]:
    source = _object(value, label)
    _exact(source, set(SOURCE_IDENTITY_FIELDS), label)
    return {
        field: require_sha256(source.get(field), field)
        for field in SOURCE_IDENTITY_FIELDS
    }


def _document(value: Mapping[str, Any], label: str) -> bytes:
    data = _canonical(dict(value))
    if len(data) > MAX_DOCUMENT_BYTES:
        raise IkBundleContractError(f"{label} exceeds its JSON resource limit")
    return data


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IkBundleContractError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise IkBundleContractError(f"{label} fields are incomplete or unsupported")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
