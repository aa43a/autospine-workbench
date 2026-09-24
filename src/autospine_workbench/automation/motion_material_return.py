"""Immutable artwork handoff bound to a live pose-material plan, never adoption."""
import base64
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile
from PIL import Image
from ..resolved_project import canonical_sha256
from .animated_store import AnimatedStore
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes, directory, publish_document, read_document

MAX_PNG = 8 << 20


def validate_png(encoded, size):
    try:
        if not isinstance(encoded, str) or len(encoded) > (MAX_PNG+2)//3*4:
            raise ValueError('size')
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > MAX_PNG:
            raise ValueError('size')
        with Image.open(BytesIO(raw)) as image:
            if (image.format != 'PNG' or list(image.size) != size or image.width*image.height > 16000000
                    or image.mode != 'RGBA' or getattr(image, 'n_frames', 1) != 1):
                raise ValueError('format_or_canvas')
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            image.load()
        return raw
    except (ValueError, OSError, Image.DecompressionBombError) as exc:
        raise PipelineRunError('motion_material_return_png_invalid') from exc


def inspect(manager, job):
    with manager._lock:
        root = manager.folder(job)/'material-returns'
        rows = []
        if root.exists():
            directory(root)
            for path in sorted(root.glob('return-*.json')):
                row = read_document(path)
                if path.name != 'return-'+canonical_sha256(row)+'.json' or row['job_id'] != job:
                    raise PipelineRunError('motion_material_return_corrupt')
                rows.append(row)
        return dict(job_id=job, returns=rows, authority='none', replacement_applied=False)


def save(manager, job, body):
    from .motion_repair_material import download
    if set(body) != {'request', 'png_base64'} or not isinstance(body['request'], dict):
        raise PipelineRunError('motion_material_return_request_invalid')
    request = body['request']
    revision = request.get('draft_revision')
    if type(revision) is not int or request.get('job_id') != job:
        raise PipelineRunError('motion_material_return_identity_changed')
    raw = validate_png(body['png_base64'], request.get('texture_size'))
    # Recheck live draft under the same lock as publication; withdrawal wins before admission.
    with manager._lock:
        with ZipFile(BytesIO(download(manager, job, str(revision), include_preview=False))) as archive:
            expected = json.loads(archive.read('request.json'))
        if request != expected:
            raise PipelineRunError('motion_material_return_identity_changed')
        if expected.get('view_needs'):
            raise PipelineRunError('motion_material_additional_view_requires_geometry_mapping')
        # Browser JSON serializes 0.0 as 0; freeze the authoritative request bytes.
        request = expected
        root = directory(manager.folder(job)/'material-returns', create=True)
        digest = sha256(raw).hexdigest()
        receipt = dict(schema='autospine.motion-material-return/v1', job_id=job,
            request_sha256=canonical_sha256(request), draft_sha256=request['draft_sha256'],
            draft_revision=revision, artifact_sha256=request['artifact_sha256'],
            slot=request['slot'], animation=request['animation'], texture_sha256=digest,
            unchanged_source=digest==request['texture_sha256'],
            status='received_pending_mapping', authority='none', replacement_applied=False)
        receipt['material_bundle_sha256'] = AnimatedStore(root).publish(
            {'request.json': canonical_bytes(request), 'replacement.png': raw})
        publish_document(root/('return-'+canonical_sha256(receipt)+'.json'), receipt, staging=root/'staging')
        return receipt
