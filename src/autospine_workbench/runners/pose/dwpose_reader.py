"""Replay recorded SimCC decoding, without claiming a repeated model inference."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import re

from ...resolved_project import canonical_sha256
from ...safe_input_files import read_real_file, strict_json_object
from .base import PoseRunnerRequest
from .dwpose_profile import PROFILE

MAX_RAW_BYTES = 12 * 1024 * 1024
_FIELDS = {"schema", "authority", "project_id", "source", "profile", "transform", "decoded",
           "simcc", "tensor_sha256", "environment", "implementation_sha256"}
_IMPLEMENTATIONS = {"dwpose.py", "dwpose_codec.py", "dwpose_adapter.py", "dwpose_profile.py"}


def _require(condition, code):
    if not condition:
        raise ValueError("dwpose_raw_" + code)


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _tensor(value, width):
    # Check every nested shape and scalar before NumPy can allocate an array.
    _require(type(value) is list and len(value) == 1 and type(value[0]) is list
             and len(value[0]) == 133, "tensor_shape_invalid")
    for row in value[0]:
        _require(type(row) is list and len(row) == width, "tensor_shape_invalid")
        for number in row:
            _require(type(number) in (float, int) and -3.4028234663852886e38 <= number <= 3.4028234663852886e38
                     and math.isfinite(number), "tensor_value_invalid")


def read_dwpose_raw(path, request):
    """Verify source bytes and replay pinned-profile decoding of immutable output.

    Implementation hashes are recorded identities, not a demand for current code
    equality. This does not establish that the model produced the saved tensors.
    """
    try:
        _require(isinstance(request, PoseRunnerRequest), "request_invalid")
        request.validate()
        path = Path(path)
        _require(re.fullmatch(r"[0-9a-f]{64}\.json", path.name) is not None, "address_invalid")
        _require(path.lstat().st_nlink == 1, "file_invalid")
        raw = read_real_file(path, MAX_RAW_BYTES, "DWPose raw result")
        document = strict_json_object(raw, "DWPose raw result")
        _require(canonical_sha256(document) == path.stem, "address_mismatch")
        _require(set(document) == _FIELDS and document["schema"] == "autospine.dwpose-raw/v1"
                 and document["authority"] == "none" and document["project_id"] == request.project_id,
                 "document_invalid")
        source = {"image_kind": "composite", "image_sha256": request.image_sha256,
                  "canvas_size": list(request.canvas_size)}
        _require(canonical_sha256(document["source"]) == canonical_sha256(source), "source_mismatch")
        _require(canonical_sha256(document["profile"]) == canonical_sha256(PROFILE), "profile_mismatch")
        implementation = document["implementation_sha256"]
        _require(type(implementation) is dict and set(implementation) == _IMPLEMENTATIONS
                 and all(_digest(value) for value in implementation.values()), "implementation_invalid")
        environment = document["environment"]
        _require(type(environment) is dict and set(environment) == {"python", "numpy", "opencv", "onnxruntime"}
                 and all(type(v) is str and 0 < len(v) <= 100 and all(32 <= ord(c) <= 126 for c in v)
                         for v in environment.values()), "environment_invalid")
        values, hashes = document["simcc"], document["tensor_sha256"]
        _require(type(values) is list and len(values) == 2 and type(hashes) is list and len(hashes) == 2
                 and all(_digest(value) for value in hashes), "tensors_invalid")
        for value, width in zip(values, (576, 768)):
            _tensor(value, width)
        import numpy as np
        from .dwpose_codec import _transform, decode_simcc

        transform = document["transform"]
        _require(canonical_sha256(transform) == canonical_sha256(_transform(*request.canvas_size)),
                 "transform_mismatch")
        tensors = [np.array(value, dtype=np.float32) for value in values]
        _require(all(hashlib.sha256(tensor.tobytes()).hexdigest() == digest
                     for tensor, digest in zip(tensors, hashes)), "tensor_hash_mismatch")
        decoded = decode_simcc(*tensors, transform)
        _require(canonical_sha256(decoded) == canonical_sha256(document["decoded"]), "decoded_mismatch")
        return deepcopy(document)
    except (OSError, RuntimeError, TypeError, KeyError, ValueError, OverflowError, RecursionError, ImportError) as exc:
        if type(exc) is ValueError and str(exc).startswith("dwpose_raw_"):
            raise
        raise ValueError("dwpose_raw_read_invalid") from exc
