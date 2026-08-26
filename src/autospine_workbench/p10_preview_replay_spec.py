"""Private absolute-path replay specification for P10 preview mounting."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class P10PreviewReplaySpec:
    """Exact persisted addresses needed to rebuild one preview from scratch."""

    state_root: Path
    project_id: str
    candidates_path: Path
    decision_path: Path
    probe_report_path: Path
    layer_manifest_sha256: str
    p3_rig_sha256: str
    p3_bundle_sha256: str
    motion_instance_sha256: str
    motion_retarget_bundle_sha256: str
    motion_instance_v2_sha256: str
    reviewed_motion_bundle_sha256: str

    @property
    def evidence_paths(self) -> tuple[Path, Path, Path]:
        return (
            self.candidates_path,
            self.decision_path,
            self.probe_report_path,
        )

    @property
    def exact_chain_kwargs(self) -> dict[str, str]:
        return {
            "layer_manifest_sha256": self.layer_manifest_sha256,
            "p3_rig_sha256": self.p3_rig_sha256,
            "p3_bundle_sha256": self.p3_bundle_sha256,
            "motion_instance_sha256": self.motion_instance_sha256,
            "motion_retarget_bundle_sha256":
                self.motion_retarget_bundle_sha256,
            "motion_instance_v2_sha256": self.motion_instance_v2_sha256,
            "reviewed_motion_bundle_sha256":
                self.reviewed_motion_bundle_sha256,
        }


def build_p10_preview_replay_spec(
    state_root: Path,
    project_id: str,
    candidates_path: Path,
    decision_path: Path,
    probe_report_path: Path,
    *,
    layer_manifest_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    motion_instance_v2_sha256: str,
    reviewed_motion_bundle_sha256: str,
) -> P10PreviewReplaySpec:
    """Copy caller addresses into an immutable, lexical absolute-path spec."""

    return P10PreviewReplaySpec(
        state_root=_absolute(state_root),
        project_id=project_id,
        candidates_path=_absolute(candidates_path),
        decision_path=_absolute(decision_path),
        probe_report_path=_absolute(probe_report_path),
        layer_manifest_sha256=layer_manifest_sha256,
        p3_rig_sha256=p3_rig_sha256,
        p3_bundle_sha256=p3_bundle_sha256,
        motion_instance_sha256=motion_instance_sha256,
        motion_retarget_bundle_sha256=motion_retarget_bundle_sha256,
        motion_instance_v2_sha256=motion_instance_v2_sha256,
        reviewed_motion_bundle_sha256=reviewed_motion_bundle_sha256,
    )


def _absolute(value: Path) -> Path:
    # Do not resolve aliases here: read_real_file must still reject them.
    return Path(os.path.abspath(os.fspath(Path(value))))
