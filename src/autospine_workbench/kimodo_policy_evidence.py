"""Compile candidate-free policy evidence from exact P7 and P8 bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .kimodo_npz_consistency import KimodoNpzConsistencyError
from .kimodo_npz_reader import KimodoNpzReaderError
from .kimodo_policy_evidence_arrays import extract_kimodo_policy_arrays
from .motion_bundle_contract import (
    MotionBundleContractError,
    build_motion_bundle_contract,
)
from .motion_bundle_integrity import VerifiedMotionBundle
from .projected_motion_bundle_contract import (
    ProjectedMotionBundleContractError,
    build_projected_motion_bundle_contract,
)
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle
from .kimodo_policy_evidence_validation import (
    FORMAT,
    FORMAT_VERSION,
    KimodoPolicyEvidenceValidationError,
    evidence_only_policy,
    require_kimodo_policy_evidence,
)


class KimodoPolicyEvidenceError(ValueError):
    """Raised when exact upstream bundles cannot form raw policy evidence."""


@dataclass(frozen=True, slots=True)
class CompiledKimodoPolicyEvidence:
    """Frozen canonical evidence document with isolated accessors."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_kimodo_policy_evidence(
    p7_bundle: VerifiedMotionBundle,
    p8_bundle: VerifiedProjectedMotionBundle,
) -> CompiledKimodoPolicyEvidence:
    """Decode exact ancillary arrays without emitting policy candidates."""

    try:
        p7_run_source, projected = _require_exact_inputs(p7_bundle, p8_bundle)
        raw = p7_bundle.raw_npz
        source = p7_bundle.kimodo_source
        if raw is None or source is None:
            raise KimodoPolicyEvidenceError(
                "Kimodo policy evidence source bytes are unavailable"
            )
        array_profile, signals = extract_kimodo_policy_arrays(raw, source)
        timing = projected["timing"]
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "clip_id": p7_bundle.clip_id,
            "source": _source_binding(p7_bundle, p8_bundle, p7_run_source),
            "array_profile": array_profile,
            "timing": {
                "ticks_per_second": timing["ticks_per_second"],
                "duration_ticks": timing["duration_ticks"],
                "frame_count": timing["frame_count"],
                "loop": timing["loop"],
                "frames": json.loads(json.dumps(projected["frames"])),
            },
            "policy": evidence_only_policy(),
            "signals": signals,
        }
        require_kimodo_policy_evidence(document)
        canonical = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        return CompiledKimodoPolicyEvidence(canonical)
    except KimodoPolicyEvidenceError:
        raise
    except (
        KimodoNpzConsistencyError,
        KimodoNpzReaderError,
        KimodoPolicyEvidenceValidationError,
        MotionBundleContractError,
        ProjectedMotionBundleContractError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise KimodoPolicyEvidenceError(
            f"Kimodo policy evidence compilation failed: {exc}"
        ) from exc


def _require_exact_inputs(p7, p8):
    if type(p7) is not VerifiedMotionBundle or p7.source_kind != "kimodo_npz":
        raise KimodoPolicyEvidenceError(
            "Kimodo policy evidence requires an exact verified P7 Kimodo bundle"
        )
    if type(p8) is not VerifiedProjectedMotionBundle:
        raise KimodoPolicyEvidenceError(
            "Kimodo policy evidence requires an exact verified P8 bundle"
        )
    p7_contract = build_motion_bundle_contract(
        p7.motion, p7.run_manifest,
        raw_npz=p7.raw_npz,
        kimodo_source=p7.kimodo_source,
        kimodo_map=p7.kimodo_map,
    )
    p8_contract = build_projected_motion_bundle_contract(
        p8.camera, p8.projected_motion, p8.run_manifest
    )
    p7_pairs = (
        (p7_contract.clip_id, p7.clip_id),
        (p7_contract.clip_sha256, p7.clip_sha256),
        (p7_contract.run_sha256, p7.run_sha256),
        (p7_contract.bundle_sha256, p7.bundle_sha256),
        (p7_contract.source_kind, p7.source_kind),
    )
    p8_pairs = (
        (p8_contract.clip_id, p8.clip_id),
        (p8_contract.projected_motion_sha256, p8.projected_motion_sha256),
        (p8_contract.camera_sha256, p8.camera_sha256),
        (p8_contract.run_sha256, p8.run_sha256),
        (p8_contract.legacy_motion_sha256, p8.legacy_motion_sha256),
        (p8_contract.bundle_sha256, p8.bundle_sha256),
    )
    if p7.inventory != p7_contract.inventory \
            or p7.document_bytes != p7_contract.document_bytes \
            or p8.inventory != p8_contract.inventory \
            or p8.document_bytes != p8_contract.document_bytes \
            or any(left != right for left, right in (*p7_pairs, *p8_pairs)):
        raise KimodoPolicyEvidenceError(
            "Verified P7/P8 identities differ from canonical content"
        )
    run_source = p7.run_manifest["source"]
    projected = p8.projected_motion
    upstream = projected["source"]
    expected = {
        "motion_ir_sha256": p7.clip_sha256,
        "motion_bundle_sha256": p7.bundle_sha256,
        "motion_run_sha256": p7.run_sha256,
        "raw_npz_sha256": run_source["raw_npz_sha256"],
        "source_sha256": run_source["source_sha256"],
        "map_sha256": run_source["map_sha256"],
        "array_inventory_sha256": run_source["array_inventory_sha256"],
    }
    if p8.p7_motion_sha256 != p7.clip_sha256 \
            or p8.p7_bundle_sha256 != p7.bundle_sha256 \
            or p8.p7_run_sha256 != p7.run_sha256 \
            or p8.legacy_motion_sha256 != p7.clip_sha256 \
            or p8.clip_id != p7.clip_id \
            or any(upstream.get(field) != value for field, value in expected.items()):
        raise KimodoPolicyEvidenceError(
            "Verified P8 projection is not cross-bound to the supplied P7 bundle"
        )
    return run_source, projected


def _source_binding(p7, p8, run_source) -> dict[str, str]:
    return {
        "p7_motion_ir_sha256": p7.clip_sha256,
        "p7_bundle_sha256": p7.bundle_sha256,
        "p7_run_sha256": p7.run_sha256,
        "raw_npz_sha256": run_source["raw_npz_sha256"],
        "kimodo_source_sha256": run_source["source_sha256"],
        "kimodo_map_sha256": run_source["map_sha256"],
        "array_inventory_sha256": run_source["array_inventory_sha256"],
        "p8_projected_motion_sha256": p8.projected_motion_sha256,
        "p8_bundle_sha256": p8.bundle_sha256,
        "p8_run_sha256": p8.run_sha256,
        "camera_sha256": p8.camera_sha256,
        "legacy_motion_ir_sha256": p8.legacy_motion_sha256,
    }
