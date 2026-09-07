"""Single full-canvas DWPose preprocessing and original 133-point SimCC decode.

Numerics follow IDEA-Research/DWPose's onnx branch, annotator/dwpose/onnxpose.py.
Transparent source pixels are composited over white before the upstream black
affine padding. No subject detection, keypoint reorder, score calibration or clamp.
"""
import math
import struct

from ...png_rgba import decode_rgba_png

INPUT_SIZE = (288, 384)
MEAN = (123.675, 116.28, 103.53)
STD = (58.395, 57.12, 57.375)


def _dependencies():
    try:
        import numpy as np
        import cv2
    except ImportError as exc:
        raise ValueError("dwpose_codec_dependencies_missing") from exc
    return np, cv2


def _transform(width, height):
    np, cv2 = _dependencies()
    center = [width * .5, height * .5]
    sw, sh = width * 1.25, height * 1.25
    if sw > sh * .75:
        sh = sw / .75
    else:
        sw = sh * .75
    cx, cy = center
    source = np.array([[cx, cy], [cx, cy-sw*.5], [cx-sw*.5, cy-sw*.5]], dtype=np.float32)
    target = np.array([[144, 192], [144, 48], [0, 48]], dtype=np.float32)
    affine = cv2.getAffineTransform(source, target)
    inverse = cv2.getAffineTransform(target, source)
    return {"profile": "dwpose-full-canvas-simcc-v1", "canvas_size": [width, height],
            "input_size": list(INPUT_SIZE), "bbox_xyxy": [0, 0, width, height],
            "center": center, "scale": [sw, sh], "padding": 1.25,
            "affine": affine.tolist(), "inverse_affine": inverse.tolist(),
            "alpha_background_rgb": [255, 255, 255], "warp_border_rgb": [0, 0, 0],
            "color_order": "BGR", "mean": list(MEAN), "std": list(STD),
            "interpolation": "INTER_LINEAR", "simcc_split_ratio": 2.0}


def preprocess_rgba(rawbytes):
    """Return contiguous float32 NCHW [1,3,384,288] and explicit inverse geometry."""
    if type(rawbytes) is not bytes or len(rawbytes) > 128 * 1024 * 1024 or len(rawbytes) < 24 \
            or rawbytes[:8] != b"\x89PNG\r\n\x1a\n" or rawbytes[12:16] != b"IHDR":
        raise ValueError("dwpose_codec_png_invalid")
    width, height = struct.unpack(">II", rawbytes[16:24])
    if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > 32 * 1024 * 1024:
        raise ValueError("dwpose_codec_image_limit")
    np, cv2 = _dependencies()
    try:
        image = decode_rgba_png(rawbytes)
        rgba = np.frombuffer(image.pixels, dtype=np.uint8).reshape(height, width, 4).astype(np.float32)
        alpha = rgba[:, :, 3:4] / 255.0
        rgb = rgba[:, :, :3] * alpha + 255.0 * (1-alpha)
        bgr = np.ascontiguousarray(np.rint(rgb).astype(np.uint8)[:, :, ::-1])
        transform = _transform(width, height)
        warped = cv2.warpAffine(bgr, np.array(transform["affine"]), INPUT_SIZE,
                                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
        normalized = (warped - np.array(MEAN, dtype=np.float32)) / np.array(STD, dtype=np.float32)
        return np.ascontiguousarray(normalized.transpose(2, 0, 1)[None], dtype=np.float32), transform
    except (TypeError, ValueError, OverflowError, struct.error) as exc:
        raise ValueError("dwpose_codec_preprocess_invalid") from exc


def decode_simcc(simcc_x, simcc_y, transform):
    """Preserve raw scores and out-of-canvas coordinates, including invalid sentinels."""
    np, _ = _dependencies()
    if type(transform) is not dict:
        raise ValueError("dwpose_codec_transform_invalid")
    canvas = transform.get("canvas_size")
    if type(canvas) is not list or len(canvas) != 2 \
            or any(type(v) is not int or not 0 < v <= 8192 for v in canvas) \
            or canvas[0]*canvas[1] > 32*1024*1024 or transform != _transform(*canvas):
        raise ValueError("dwpose_codec_transform_invalid")
    for tensor, shape in ((simcc_x, (1, 133, 576)), (simcc_y, (1, 133, 768))):
        if not isinstance(tensor, np.ndarray) or tensor.shape != shape \
                or tensor.dtype.kind != "f" or not np.isfinite(tensor).all():
            raise ValueError("dwpose_codec_simcc_invalid")
    scores = np.minimum(simcc_x.max(axis=2), simcc_y.max(axis=2))[0]
    locations = np.stack((simcc_x.argmax(axis=2)[0], simcc_y.argmax(axis=2)[0]), axis=-1).astype(np.float32)
    locations[scores <= 0] = -1
    keypoints = locations / 2.0
    keypoints = keypoints / np.array(INPUT_SIZE) * np.array(transform["scale"]) \
        + np.array(transform["center"]) - np.array(transform["scale"]) / 2
    if not np.isfinite(keypoints).all() or any(not math.isfinite(float(score)) for score in scores):
        raise ValueError("dwpose_codec_result_invalid")
    return {"keypoints133": keypoints.tolist(), "scores133": scores.tolist(),
            "valid133": (scores > 0).tolist(), "score_kind": "raw_simcc_minimum",
            "coordinate_system": "source_canvas_xy", "keypoint_order": "coco_wholebody_133"}
