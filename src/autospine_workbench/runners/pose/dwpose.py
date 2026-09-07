"""Explicit CPU ONNX producer; run inside the isolated pose environment."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import platform

from ...artifact_store import ImmutableJsonArtifactStore
from ...automation.storage_io import directory
from ...coco17_adapter import adapt_coco17_detections
from ...coco17_detections import load_coco17_detections
from ...pose_observations import load_pose_observations
from ...safe_input_files import read_real_file, strict_json_object
from ...manifest_artifacts import require_safe_token
from ...resolved_project import canonical_sha256
from ...spine42_v3_bundle_files import existing_exact_child
from .base import PoseRunnerRequest
from .dwpose_adapter import to_coco17
from .dwpose_profile import MODEL_BYTES, MODEL_SHA256, PROFILE


def _publish(state_root, kind, project_id, document):
    require_safe_token(project_id, 'Pose project')
    if kind not in ('dwpose-raw', 'pose-adapter-inputs', 'pose-observations'):
        raise ValueError('dwpose_artifact_kind_invalid')
    current = directory(Path(state_root), create=True)
    for name in ('analysis', project_id, kind):
        existing_exact_child(current, name)
        current = directory(current / name, create=True)
    digest = canonical_sha256(document)
    existing = existing_exact_child(current, digest + '.json')
    if existing is not None:
        if existing.lstat().st_nlink != 1:
            raise ValueError('dwpose_artifact_alias')
        read_real_file(existing, 12 * 1024 * 1024, 'Pose artifact')
    result = ImmutableJsonArtifactStore(state_root).publish(kind, project_id, document)
    actual = strict_json_object(read_real_file(result.path, 12 * 1024 * 1024, 'Pose artifact'), 'Pose artifact')
    if result.path.lstat().st_nlink != 1 or canonical_sha256(actual) != digest:
        raise ValueError('dwpose_artifact_changed')
    return result


@dataclass(frozen=True)
class DWPoseOnnxRunner:
    model: Path
    state_root: Path
    mirror_state: str = 'unknown'
    view_orientation: str = 'unknown'
    runner_id = 'dwpose-wholebody-fullcanvas-v1'

    def produce(self, request: PoseRunnerRequest) -> Path:
        request.validate()
        if self.mirror_state not in ('unknown', 'mirrored', 'not_mirrored') \
                or self.view_orientation not in ('unknown', 'front', 'three_quarter', 'back', 'left_profile', 'right_profile'):
            raise ValueError('dwpose_declaration_invalid')
        model = read_real_file(self.model, MODEL_BYTES, 'DWPose ONNX')
        if len(model) != MODEL_BYTES or hashlib.sha256(model).hexdigest() != MODEL_SHA256:
            raise ValueError('dwpose_model_identity_mismatch')
        image = read_real_file(request.input_image, 128 * 1024 * 1024, 'DWPose image')
        if hashlib.sha256(image).hexdigest() != request.image_sha256:
            raise ValueError('dwpose_image_changed')
        # Optional inference dependencies never enter the core import closure.
        import cv2
        import numpy as np
        import onnxruntime as ort
        from .dwpose_codec import preprocess_rgba, decode_simcc

        tensor, transform = preprocess_rgba(image)
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        session = ort.InferenceSession(model, sess_options=options, providers=['CPUExecutionProvider'])
        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].shape not in ([1, 3, 384, 288], ['batch', 3, 384, 288]) \
                or inputs[0].type != 'tensor(float)':
            raise ValueError('dwpose_model_interface_mismatch')
        outputs = session.run(['simcc_x', 'simcc_y'], {inputs[0].name: tensor})
        if len(outputs) != 2:
            raise ValueError('dwpose_model_output_mismatch')
        decoded = decode_simcc(*outputs, transform)
        raw = {'schema': 'autospine.dwpose-raw/v1', 'authority': 'none', 'project_id': request.project_id,
               'source': {'image_kind': 'composite', 'image_sha256': request.image_sha256,
                          'canvas_size': list(request.canvas_size)},
               'profile': PROFILE, 'transform': transform, 'decoded': decoded,
               'simcc': [value.tolist() for value in outputs],
               'tensor_sha256': [hashlib.sha256(v.tobytes()).hexdigest() for v in outputs],
               'environment': {'python': platform.python_version(), 'numpy': np.__version__,
                               'opencv': cv2.__version__, 'onnxruntime': ort.__version__},
               'implementation_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                         for name in ('dwpose.py', 'dwpose_codec.py', 'dwpose_adapter.py', 'dwpose_profile.py')}}
        saved_raw = _publish(self.state_root, 'dwpose-raw', request.project_id, raw)
        from .dwpose_reader import read_dwpose_raw
        read_dwpose_raw(saved_raw.path, request)
        coco = _publish(self.state_root, 'pose-adapter-inputs', request.project_id, to_coco17(raw))
        context = {'expected_project_id': request.project_id, 'expected_image_sha256': request.image_sha256,
                   'expected_canvas_size': request.canvas_size}
        detections = load_coco17_detections(coco.path, **context)
        document = adapt_coco17_detections(detections, selected_index=0, selection_method='single',
                                         side_mapping='as_reported', view_orientation=self.view_orientation,
                                         mirror_state=self.mirror_state)
        pose = _publish(self.state_root, 'pose-observations', request.project_id, document)
        load_pose_observations(pose.path, **context)
        return pose.path
