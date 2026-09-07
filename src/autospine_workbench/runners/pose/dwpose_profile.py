"""Pinned, opt-in single-image DWPose profile; no downloader at import time."""
MODEL_REVISION = '1a7144101628d69ee7a3768d1ee3a094070dc388'
UPSTREAM_COMMIT = '3dca5db79d9f9ffdd378753ddf6ec66535aace88'
MODEL_SHA256 = '724f4ff2439ed61afb86fb8a1951ec39c6220682803b4a8bd4f598cd913b1843'
MODEL_BYTES = 134399116
MODEL_URL = f'https://huggingface.co/yzd-v/DWPose/resolve/{MODEL_REVISION}/dw-ll_ucoco_384.onnx'
PROFILE = {
    'id': 'dwpose-wholebody-fullcanvas-v1', 'upstream_commit': UPSTREAM_COMMIT,
    'model_revision': MODEL_REVISION, 'model_sha256': MODEL_SHA256,
    'subject_policy': 'assumed_single_full_canvas_not_person_detection',
    'alpha_background': 'white', 'network_color': 'BGR', 'padding': 1.25,
    'input_size_wh': [288, 384], 'simcc_split_ratio': 2,
    'provider': 'CPUExecutionProvider', 'threads': 1,
    'visibility': 'unknown', 'score_calibrated': False,
    'canonical_score_mapping': 'positive-simcc-s-over-one-plus-s-v1',
}
