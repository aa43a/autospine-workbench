"""Retain raw WholeBody output; admit only representable COCO17 observations."""
import math

from ...resolved_project import canonical_sha256
from .dwpose_profile import MODEL_REVISION, MODEL_SHA256, PROFILE


def to_coco17(raw):
    if raw.get('schema') != 'autospine.dwpose-raw/v1' or raw.get('authority') != 'none' \
            or raw.get('profile') != PROFILE:
        raise ValueError('dwpose_raw_profile_invalid')
    points, scores = raw['decoded']['keypoints133'], raw['decoded']['scores133']
    canvas = raw['source']['canvas_size']
    if len(points) != 133 or len(scores) != 133:
        raise ValueError('dwpose_raw_shape_invalid')
    for point, score in zip(points, scores):
        if len(point) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point) \
                or type(score) not in (int, float) or not math.isfinite(score):
            raise ValueError('dwpose_raw_nonfinite')
    # Do not clip predictions or invent image coordinates for an invalid detection.
    for point, score in zip(points[:17], scores[:17]):
        if not score > 0 or any(not 0 <= v < limit for v, limit in zip(point, canvas)):
            raise ValueError('dwpose_coco17_unrepresentable')
    return {
        'format': 'autospine-coco17-detections', 'format_version': 1,
        'project_id': raw['project_id'], 'source': raw['source'],
        'detector': {'id': 'dwpose-wholebody-onnx', 'version': '1',
                     'model_revision': MODEL_REVISION, 'model_sha256': MODEL_SHA256,
                     'config_sha256': canonical_sha256({'profile': PROFILE, 'raw_sha256': canonical_sha256(raw)}),
                     'runtime': 'onnxruntime-' + raw['environment']['onnxruntime'] + '-cpu'},
        'coordinate_system': {'origin': 'top_left', 'x_axis': 'right', 'y_axis': 'down',
                              'units': 'pixel', 'side_naming': 'coco_character_side', 'image_space': 'project_canvas'},
        'detected_count': 1,
        # SimCC peaks are not probabilities and can exceed one. This explicit
        # monotone encoding fits the old contract; it is NOT confidence calibration.
        'detections': [{'keypoints': points[:17], 'keypoint_scores': [s / (1 + s) for s in scores[:17]],
                        'visibility': ['unknown'] * 17, 'bbox_xywh': [0, 0, *canvas]}],
    }
