"""Bounded 16 MiB immutable mesh documents, without enlarging legacy journals."""
import os
from pathlib import Path
import tempfile

from ..automation.storage_io import canonical_bytes,directory
from ..manifest_artifacts import require_safe_token,require_sha256
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file,strict_json_object
from ..spine42_v3_bundle_files import existing_exact_child
from .artifacts import _folder

MAX_BYTES=16*1024*1024
KIND='weighted-mesh-candidates'
DISTAL_GRID_SCHEMA='autospine.distal-grid-experiment/v1'
SCHEMAS=('autospine.weighted-mesh-candidates/v1','autospine.weighted-mesh-refinement/v1','autospine.elbow-bake/v1','autospine.partition-mesh/v1','autospine.distal-corrective/v1')
SCHEMAS += (DISTAL_GRID_SCHEMA,)
SCHEMAS += ('autospine.distal-width-experiment/v1',)
SCHEMAS += ('autospine.layer-partitions/v2',)
SCHEMAS += ('autospine.ownership-atlas/v1',)


def _read(path):
    directory(path.parent)
    exact=existing_exact_child(path.parent,path.name)
    if exact is None or exact.lstat().st_nlink!=1:
        raise ValueError('mesh_storage_invalid')
    raw=read_real_file(exact,MAX_BYTES,'mesh document')
    doc=strict_json_object(raw,'mesh document')
    if canonical_bytes(doc)!=raw or doc.get('schema') not in SCHEMAS or doc.get('authority')!='none' or doc.get('production_authorized') is not False:
        raise ValueError('mesh_storage_invalid')
    return doc


def _publish(path,doc):
    raw=canonical_bytes(doc)
    if len(raw)>MAX_BYTES:raise ValueError('mesh_document_too_large')
    if doc.get('schema') not in SCHEMAS or doc.get('authority')!='none' or doc.get('production_authorized') is not False:
        raise ValueError('mesh_storage_invalid')
    folder=directory(path.parent,create=True)
    staging=directory(folder/'.mesh-staging',create=True)
    descriptor,name=tempfile.mkstemp(prefix='pending-',dir=staging)
    temporary=Path(name)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        if existing_exact_child(folder,path.name) is None:
            try:os.link(temporary,path)
            except FileExistsError:pass
    finally:temporary.unlink(missing_ok=True)
    if _read(path)!=doc:raise ValueError('mesh_output_exists')


def publish_mesh_report(state,dataset,doc):
    require_safe_token(dataset,'Dataset id')
    digest=canonical_sha256(doc)
    folder=_folder(state,dataset,KIND,create=True)
    _publish(folder/(digest+'.json'),doc)
    return digest


def read_mesh_report(state,dataset,digest):
    require_safe_token(dataset,'Dataset id');require_sha256(digest,'Mesh digest')
    doc=_read(_folder(state,dataset,KIND)/(digest+'.json'))
    if canonical_sha256(doc)!=digest:raise ValueError('mesh_storage_invalid')
    return doc


def export_mesh(path,doc):
    _publish(Path(path).absolute(),doc)
