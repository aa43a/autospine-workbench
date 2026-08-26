"""Reusable exact-content admission boundary for verified P3 mesh bundles."""

from __future__ import annotations

from typing import Any

from .mesh_bundle_contract import build_mesh_bundle_contract
from .mesh_bundle_integrity import VerifiedMeshBundle
from .rig_validation import RigSemanticValidator


class MeshBundleAdmissionError(ValueError):
    """Raised when a nominally verified P3 value differs from its content."""


def require_exact_mesh_bundle(bundle: VerifiedMeshBundle) -> dict[str, Any]:
    """Rebuild a P3 bundle contract and return an isolated admitted RigIR."""

    try:
        if type(bundle) is not VerifiedMeshBundle:
            raise MeshBundleAdmissionError(
                "P3 admission requires an exact VerifiedMeshBundle"
            )
        rig, run = bundle.rig, bundle.run_manifest
        contract = build_mesh_bundle_contract(
            bundle.project_id, rig, run, bundle.probes,
            bundle.visuals, bundle.pngs,
        )
        document_bytes = {
            name: text.encode("utf-8")
            for name, text in bundle._document_json_items
        }
        checks = (
            (contract.project_id, bundle.project_id),
            (contract.rig_sha256, bundle.rig_sha256),
            (contract.run_sha256, bundle.run_sha256),
            (contract.probes_sha256, bundle.probes_sha256),
            (contract.visuals_sha256, bundle.visuals_sha256),
            (contract.bundle_sha256, bundle.bundle_sha256),
        )
        expected_inputs = {
            "base_rig_sha256": bundle.base_rig_sha256,
            "base_bundle_sha256": bundle.base_bundle_sha256,
            "layer_manifest_sha256": bundle.layer_manifest_sha256,
            "resolved_project_sha256": bundle.resolved_project_sha256,
        }
        errors = [
            issue for issue in RigSemanticValidator().validate(rig)
            if issue.severity == "error"
        ]
        if errors or contract.document_bytes != document_bytes \
                or contract.png_bytes_by_path != bundle.pngs \
                or contract.inventory != bundle.inventory \
                or any(left != right for left, right in checks) \
                or run.get("inputs") != expected_inputs:
            raise MeshBundleAdmissionError(
                "Verified P3 bundle differs from its canonical content"
            )
        return rig
    except MeshBundleAdmissionError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise MeshBundleAdmissionError(
            f"P3 bundle admission failed: {exc}"
        ) from exc
