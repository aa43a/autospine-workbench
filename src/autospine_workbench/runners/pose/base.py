"""Explicit pose producers return canonical files; import does not infer pose."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Protocol, runtime_checkable

from ...png_rgba import RgbaPngError, decode_rgba_png
from ...pose_observations import MAX_POSE_DOCUMENT_BYTES, load_pose_observations
from ...safe_input_files import SafeInputFileError, read_real_file, strict_json_object

MAX_INPUT_IMAGE_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class PoseRunnerRequest:
    project_id: str
    image_sha256: str
    canvas_size: tuple[int, int]
    input_image: Path

    def validate(self):
        """Verify the exact image snapshot before an explicit producer runs."""
        if type(self.project_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.project_id) is None \
                or type(self.image_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", self.image_sha256) is None \
                or type(self.canvas_size) is not tuple or len(self.canvas_size) != 2 \
                or any(type(v) is not int or not 0 < v <= 4096 for v in self.canvas_size) \
                or not isinstance(self.input_image, Path):
            raise ValueError("pose_runner_request_invalid")
        try:
            raw = read_real_file(self.input_image, MAX_INPUT_IMAGE_BYTES, "pose runner source image")
        except (SafeInputFileError, OSError) as exc:
            raise ValueError("pose_runner_image_unavailable") from exc
        if hashlib.sha256(raw).hexdigest() != self.image_sha256:
            raise ValueError("pose_runner_image_changed")
        try:
            image = decode_rgba_png(raw)
        except RgbaPngError as exc:
            raise ValueError("pose_runner_image_invalid") from exc
        if (image.width, image.height) != self.canvas_size:
            raise ValueError("pose_runner_canvas_mismatch")
        return self


@runtime_checkable
class ModelRunner(Protocol):
    """An explicitly selected isolated producer; never auto-download on import."""
    runner_id: str

    def produce(self, request: PoseRunnerRequest) -> Path:
        """Return a canonical pose-observations file bound to request's image."""
        ...


@dataclass(frozen=True)
class CanonicalPoseFileImporter:
    """Read an existing observation file without running a model or writing it."""
    path: Path
    runner_id = "canonical-pose-file-importer-v1"

    def produce(self, request: PoseRunnerRequest) -> Path:
        if not isinstance(request, PoseRunnerRequest) or not isinstance(self.path, Path):
            raise ValueError("pose_runner_request_invalid")
        request.validate()
        try:
            before = read_real_file(self.path, MAX_POSE_DOCUMENT_BYTES, "canonical pose import")
        except (SafeInputFileError, OSError) as exc:
            raise ValueError("pose_runner_observations_unavailable") from exc
        try:
            strict_json_object(before, "canonical pose import")
            load_pose_observations(self.path, expected_project_id=request.project_id,
                                   expected_image_sha256=request.image_sha256,
                                   expected_canvas_size=request.canvas_size)
        except (ValueError, OverflowError, RecursionError) as exc:
            raise ValueError("pose_runner_observations_invalid") from exc
        try:
            after = read_real_file(self.path, MAX_POSE_DOCUMENT_BYTES, "canonical pose import")
        except (SafeInputFileError, OSError) as exc:
            raise ValueError("pose_runner_observations_unavailable") from exc
        if before != after:
            raise ValueError("pose_runner_observations_changed")
        return self.path
