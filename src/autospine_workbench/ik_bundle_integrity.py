"""Reproducibility verification for one snapshotted immutable P4 bundle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .ik_bundle_contract import (
    DOCUMENT_NAMES,
    IkBundleContractError,
    build_ik_bundle_contract,
)
from .ik_probe_report import (
    IkProbeReportError,
    build_ik_probe_report,
    require_ik_probe_report,
)
from .ik_target_geometry import SOURCE_IDENTITY_FIELDS
from .ik_target_profile import compile_ik_target_profile
from .ik_target_profile_validation import (
    IkTargetProfileValidationError,
    require_ik_target_profile,
)
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)


class IkBundleIntegrityError(ValueError):
    """Raised when stored P4 bytes cannot be rebuilt from their exact P3 source."""


@dataclass(frozen=True, slots=True)
class IkBundleSnapshot:
    """The single admitted read of every file in a secured P4 directory."""

    directory: Path
    document_items: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedIkBundle:
    """Frozen verified P4 identities with isolated document accessors."""

    path: Path
    project_id: str
    profile_sha256: str
    probes_sha256: str
    bundle_sha256: str
    p3_rig_sha256: str
    p3_bundle_sha256: str
    _source_json: str = field(repr=False)
    _document_json_items: tuple[tuple[str, str], ...] = field(repr=False)

    def _document(self, name: str) -> dict[str, Any]:
        return json.loads(dict(self._document_json_items)[name])

    @property
    def profile(self) -> dict[str, Any]:
        return self._document("profile.json")

    @property
    def probes(self) -> dict[str, Any]:
        return self._document("probes.json")

    @property
    def source_identities(self) -> dict[str, str]:
        return json.loads(self._source_json)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _value in self._document_json_items)


def verify_ik_bundle_snapshot(
    snapshot: IkBundleSnapshot,
    *,
    state_root: Path,
    expected_project_id: str,
    expected_profile_sha256: str,
    expected_bundle_sha256: str,
) -> VerifiedIkBundle:
    """Validate address and bytes, then rebuild both documents from strict P3."""

    try:
        if not isinstance(snapshot, IkBundleSnapshot):
            raise IkBundleIntegrityError("IK bundle snapshot is invalid")
        raw = _exact_items(snapshot.document_items)
        documents = {
            name: _strict_json(data, name) for name, data in raw.items()
        }
        profile, probes = (documents[name] for name in DOCUMENT_NAMES)
        contract = build_ik_bundle_contract(
            expected_project_id, profile, probes
        )
        if contract.document_bytes != raw:
            raise IkBundleIntegrityError(
                "IK bundle JSON bytes are not strict canonical snapshots"
            )
        if (
            contract.project_id != expected_project_id
            or contract.profile_sha256 != expected_profile_sha256
            or contract.bundle_sha256 != expected_bundle_sha256
        ):
            raise IkBundleIntegrityError(
                "IK bundle differs from its requested content address"
            )
        _require_address(snapshot.directory, contract)
        source = _source(profile.get("source"))
        p3 = VerifiedMeshBundleReader(Path(state_root)).load(
            expected_project_id,
            source["rig_sha256"],
            source["bundle_sha256"],
        )
        require_ik_target_profile(profile, verified_bundle=p3)
        rebuilt_profile = compile_ik_target_profile(p3).document
        if _canonical(rebuilt_profile) != raw["profile.json"]:
            raise IkBundleIntegrityError(
                "Stored IK profile differs from exact current P3 dependencies"
            )
        rebuilt_probes = build_ik_probe_report(rebuilt_profile).document
        require_ik_probe_report(probes, profile=rebuilt_profile)
        if _canonical(rebuilt_probes) != raw["probes.json"]:
            raise IkBundleIntegrityError(
                "Stored IK probes differ from recomputed numerical evidence"
            )
        items = tuple(
            (name, raw[name].decode("utf-8")) for name in DOCUMENT_NAMES
        )
        return VerifiedIkBundle(
            path=snapshot.directory,
            project_id=contract.project_id,
            profile_sha256=contract.profile_sha256,
            probes_sha256=contract.probes_sha256,
            bundle_sha256=contract.bundle_sha256,
            p3_rig_sha256=p3.rig_sha256,
            p3_bundle_sha256=p3.bundle_sha256,
            _source_json=_encode(source),
            _document_json_items=items,
        )
    except IkBundleIntegrityError:
        raise
    except (
        IkBundleContractError,
        IkProbeReportError,
        IkTargetProfileValidationError,
        VerifiedMeshBundleReaderError,
        AttributeError,
        KeyError,
        OverflowError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise IkBundleIntegrityError(
            f"IK bundle integrity verification failed: {exc}"
        ) from exc


def _strict_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise IkBundleIntegrityError(
                        f"IK bundle JSON contains a duplicate key: {label}"
                    )
                result[key] = value
            return result

        def nonfinite(value):
            raise IkBundleIntegrityError(
                f"IK bundle JSON contains a non-finite number: {label}"
            )

        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=nonfinite,
        )
    except IkBundleIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise IkBundleIntegrityError(
            f"IK bundle JSON is invalid: {label}"
        ) from exc
    if not isinstance(value, dict):
        raise IkBundleIntegrityError(
            f"IK bundle JSON must be an object: {label}"
        )
    return value


def _exact_items(items) -> dict[str, bytes]:
    if not isinstance(items, tuple):
        raise IkBundleIntegrityError("IK bundle snapshot inventory is invalid")
    result = {}
    for key, value in items:
        if not isinstance(key, str) or key in result or not isinstance(value, bytes):
            raise IkBundleIntegrityError("IK bundle snapshot inventory is invalid")
        result[key] = value
    if set(result) != set(DOCUMENT_NAMES):
        raise IkBundleIntegrityError("IK bundle document snapshot is incomplete")
    return result


def _source(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(SOURCE_IDENTITY_FIELDS):
        raise IkBundleIntegrityError("IK profile source identities are invalid")
    if any(not isinstance(value[field], str) for field in SOURCE_IDENTITY_FIELDS):
        raise IkBundleIntegrityError("IK profile source identities are invalid")
    return {field: value[field] for field in SOURCE_IDENTITY_FIELDS}


def _require_address(path: Path, contract) -> None:
    if (
        path.name != contract.bundle_sha256
        or path.parent.name != contract.profile_sha256
        or path.parent.parent.name != "ik-targets"
        or path.parent.parent.parent.name != contract.project_id
    ):
        raise IkBundleIntegrityError(
            "IK bundle content-address path is invalid"
        )


def _canonical(value: Any) -> bytes:
    return _encode(value).encode("utf-8")


def _encode(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
