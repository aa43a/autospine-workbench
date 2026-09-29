"""In-process handoff of freshly computed geometry, bound to the whole bundle."""
from dataclasses import dataclass
from hashlib import sha256
import json

from ..resolved_project import canonical_sha256
from .storage_io import canonical_bytes


@dataclass(frozen=True)
class GeometryEvidence:
    bundle_sha256: str
    geometry_bytes: bytes


def prepared(files, geometry):
    raw = canonical_bytes(geometry)
    if (files.get('deformation.json') != raw or
            geometry.get('skeleton_sha256') != sha256(files['skeleton.json']).hexdigest()):
        raise ValueError('character_capture_geometry_source_mismatch')
    return GeometryEvidence(canonical_sha256({name: sha256(raw).hexdigest()
                                             for name, raw in files.items()}), raw)


def reuse(evidence, files, digest):
    if (type(evidence) is not GeometryEvidence or evidence.bundle_sha256 != digest or
            canonical_sha256({name: sha256(raw).hexdigest() for name, raw in files.items()}) != digest or
            files.get('deformation.json') != evidence.geometry_bytes):
        raise ValueError('character_capture_geometry_source_mismatch')
    geometry = json.loads(evidence.geometry_bytes)
    if geometry.get('skeleton_sha256') != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('character_capture_geometry_source_mismatch')
    return geometry
