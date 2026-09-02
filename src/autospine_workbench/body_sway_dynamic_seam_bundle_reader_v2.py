"""Exact historical reader for immutable P10.5d v2 bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from .body_sway_dynamic_seam_bundle_contract_v2 import (
    DOCUMENT_NAMES,
    BodySwayDynamicSeamBundleContractV2Error,
    build_body_sway_dynamic_seam_bundle_contract_v2,
)
from .body_sway_dynamic_seam_bundle_fs_v2 import (
    BodySwayDynamicSeamBundleFSV2Error,
    body_sway_dynamic_seam_bundle_fs_v2,
)
from .immutable_bundle_fs import ImmutableBundleFSError
from .safe_input_files import SafeInputFileError, strict_json_object


class BodySwayDynamicSeamBundleReaderV2Error(RuntimeError):
    """Raised when historical P10.5d v2 bytes cannot replay exactly."""


@dataclass(frozen=True, slots=True)
class VerifiedBodySwayDynamicSeamBundleV2:
    path: Path
    project_id: str
    clip_id: str
    source_set_sha256: str
    source_document_sha256: str
    probe_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def source(self) -> dict:
        return json.loads(dict(self._documents)[DOCUMENT_NAMES[0]])

    @property
    def probe(self) -> dict:
        return json.loads(dict(self._documents)[DOCUMENT_NAMES[1]])

    @property
    def manifest(self) -> dict:
        return json.loads(dict(self._documents)[DOCUMENT_NAMES[2]])


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamBundleReaderV2:
    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self, project_id: str, probe_sha256: str, bundle_sha256: str,
    ) -> VerifiedBodySwayDynamicSeamBundleV2:
        """Validate only explicit historical bytes, never a latest alias."""

        try:
            snapshot = body_sway_dynamic_seam_bundle_fs_v2(
                self.state_root, project_id,
            ).read(probe_sha256, bundle_sha256)
            source = strict_json_object(
                snapshot.file_bytes(DOCUMENT_NAMES[0]),
                "dynamic seam v2 bundle source",
            )
            probe = strict_json_object(
                snapshot.file_bytes(DOCUMENT_NAMES[1]),
                "dynamic seam v2 bundle probe",
            )
            strict_json_object(
                snapshot.file_bytes(DOCUMENT_NAMES[2]),
                "dynamic seam v2 bundle manifest",
            )
            contract = build_body_sway_dynamic_seam_bundle_contract_v2(
                source, probe,
            )
            if contract.project_id != project_id \
                    or contract.probe_sha256 != probe_sha256 \
                    or contract.bundle_sha256 != bundle_sha256 \
                    or contract.document_bytes != {
                        name: snapshot.file_bytes(name)
                        for name in DOCUMENT_NAMES
                    }:
                raise BodySwayDynamicSeamBundleReaderV2Error(
                    "Dynamic seam v2 bundle differs from exact address"
                )
            manifest = contract.manifest
            if manifest["authority_scope"] \
                    != "historical_exact_bytes_only" \
                    or any(manifest["claims"].values()):
                raise BodySwayDynamicSeamBundleReaderV2Error(
                    "Historical dynamic seam v2 bundle overclaims authority"
                )
            return VerifiedBodySwayDynamicSeamBundleV2(
                snapshot.path, contract.project_id, contract.clip_id,
                contract.source_set_sha256,
                contract.source_document_sha256,
                contract.probe_sha256, contract.bundle_sha256,
                tuple((name, snapshot.file_bytes(name))
                      for name in DOCUMENT_NAMES),
            )
        except BodySwayDynamicSeamBundleReaderV2Error:
            raise
        except (
            BodySwayDynamicSeamBundleContractV2Error,
            BodySwayDynamicSeamBundleFSV2Error,
            ImmutableBundleFSError, KeyError, OSError, OverflowError,
            RecursionError, RuntimeError, SafeInputFileError,
            TypeError, UnicodeError, ValueError,
        ) as exc:
            raise BodySwayDynamicSeamBundleReaderV2Error(
                "Dynamic seam v2 historical bundle verification failed"
            ) from exc


__all__ = [
    "BodySwayDynamicSeamBundleReaderV2",
    "BodySwayDynamicSeamBundleReaderV2Error",
    "VerifiedBodySwayDynamicSeamBundleV2",
]
