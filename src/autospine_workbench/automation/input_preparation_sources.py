"""Project-local audit input preparation, with no benchmark mapping assertion."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from pathlib import Path

from ..benchmark.artifacts import publish_report
from ..benchmark.semantic_candidates import _layers
from ..manifest_artifacts import require_safe_token, require_sha256
from ..png_rgba import decode_rgba_png
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file, strict_json_object
from . import animated_inputs as inputs
from .animated_store import AnimatedStore
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes


class SourceStore(AnimatedStore):
    def __init__(self, state_root):
        super().__init__(state_root)
        self.root = Path(state_root) / 'input-preparation' / 'source-bundles'


@dataclass(frozen=True)
class PreparedSource:
    candidate: dict
    audit: dict
    manifest: dict
    checkpoint: dict
    composite: bytes
    composite_path: Path
    assert_current: object


def build_candidate(manifest, audit, files):
    """Use name-only suggestions while explicitly identifying audit/composite input."""
    validate_source_manifest(manifest)
    if (manifest.get('schema') != 'autospine.project-audit-source/v1' or
        manifest.get('authority') != 'none' or manifest.get('scope') != 'project_input' or
        manifest['audit_sha256'] != canonical_sha256(audit)):
        raise inputs.AnimatedSourceError('input_preparation_source_invalid')
    records = []
    observed = [row for row in audit['layers'] if row.get('kind') == 'pixel']
    if set(files) != {'audit.json', 'composite.png', *(f'layers/layer-{i:03d}.png' for i in range(len(observed)))}:
        raise inputs.AnimatedSourceError('input_preparation_source_invalid')
    composite = decode_rgba_png(files['composite.png'])
    if [composite.width, composite.height] != audit['canvas'] or max(audit['canvas']) > 4096:
        raise inputs.AnimatedSourceError('input_preparation_canvas_mismatch')
    for index, row in enumerate(observed):
        path = f'layers/layer-{index:03d}.png'
        raw = files[path]
        image = decode_rgba_png(raw)
        box = row['bbox']
        if [image.width, image.height] != [max(1, box[2] - box[0]), max(1, box[3] - box[1])]:
            raise inputs.AnimatedSourceError('input_preparation_layer_canvas_mismatch')
        records.append({key: deepcopy(row[key]) for key in ('index', 'traversal_index', 'name', 'bbox')})
        records[-1]['image'] = dict(path=path, sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw))
    layers = _layers(records, audit['layers'], audit['canvas'])
    envelope = dict(schema='autospine.benchmark-audit-snapshot/v1', authority='none', payload=audit)
    return dict(schema='autospine.project-semantic-candidates/v1', authority='none',
                source_kind='project_audit', dataset_id=manifest['dataset_id'], character_id=manifest['project_id'],
                benchmark_manifest_sha256=canonical_sha256(manifest),
                audit_snapshot_sha256=canonical_sha256(audit), audit_envelope_sha256=canonical_sha256(envelope),
                source_psd_sha256=audit['sha256'], composite_sha256=hashlib.sha256(files['composite.png']).hexdigest(),
                canvas=deepcopy(audit['canvas']), coordinate_system='psd_canvas',
                algorithm_profile='exact-layer-name-v1', review_required=True, layers=layers)


def validate_source_manifest(value):
    fields = {'schema', 'authority', 'scope', 'dataset_id', 'project_id', 'audit_sha256',
              'source_bundle_sha256', 'source_image_kind', 'original_png_mapping', 'original_psd_bytes'}
    if (type(value) is not dict or set(value) != fields or
        value['schema'] != 'autospine.project-audit-source/v1' or value['authority'] != 'none' or
        value['scope'] != 'project_input' or value['source_image_kind'] != 'audit_composite' or
        value['original_png_mapping'] != 'not_asserted' or value['original_psd_bytes'] != 'not_asserted'):
        raise inputs.AnimatedSourceError('input_preparation_source_invalid')
    for field in ('dataset_id', 'project_id'):
        require_safe_token(value[field], field)
    for field in ('audit_sha256', 'source_bundle_sha256'):
        require_sha256(value[field], field)


def prepare_source(store, project_id, expected_resolved_sha256):
    """Capture actual audit rasters. No PNG/PSD matching or benchmark split is invented."""
    try:
        project, checkpoint = inputs._checkpoint(store, project_id)
        if checkpoint['resolved_project_sha256'] != expected_resolved_sha256:
            raise inputs.AnimatedSourceError('input_preparation_source_stale')
        try:
            inputs._registrations(store, project_id)
        except inputs.AnimatedSourceError as exc:
            if exc.reason_code != 'animated_source_missing':
                raise
        else:
            raise inputs.AnimatedSourceError('input_preparation_already_registered')
        if project['overrides']['revision'] != 0:
            raise inputs.AnimatedSourceError('input_preparation_authoring_edits_unsupported')
        audit = deepcopy(store._record(project_id).audit)
        files = {'audit.json': canonical_bytes(audit)}
        files['composite.png'] = read_real_file(Path(store.resolve_asset(project_id, 'composite')), 64 << 20, 'source composite')
        for index, row in enumerate(project['layers']):
            files[f'layers/layer-{index:03d}.png'] = read_real_file(
                Path(store.resolve_asset(project_id, 'layer', row['id'])), 64 << 20, 'source layer')
        source_store = SourceStore(store.state_root)
        digest = source_store.publish(files)
        manifest = dict(schema='autospine.project-audit-source/v1', authority='none', scope='project_input',
                        dataset_id='project-audit-' + canonical_sha256({'project_id': project_id, 'audit': audit})[:24],
                        project_id=project_id, audit_sha256=canonical_sha256(audit), source_bundle_sha256=digest,
                        source_image_kind='audit_composite', original_png_mapping='not_asserted',
                        original_psd_bytes='not_asserted')
        candidate = build_candidate(manifest, audit, files)
        inputs._match_audit(store, project_id, candidate)

        def assert_current():
            if inputs._checkpoint(store, project_id)[1] != checkpoint:
                raise inputs.AnimatedSourceError('input_preparation_source_stale')
            inputs._match_audit(store, project_id, candidate)

        assert_current()
        publish_report(store.state_root, manifest['dataset_id'], 'project-input-sources', manifest)
        return PreparedSource(candidate, audit, manifest, checkpoint, files['composite.png'],
                              source_store.root / digest / 'composite.png', assert_current)
    except inputs.AnimatedSourceError:
        raise
    except (PipelineRunError, ValueError, KeyError, TypeError, OSError) as exc:
        raise inputs.AnimatedSourceError('input_preparation_source_invalid') from exc


def read_source(store, manifest):
    try:
        files = SourceStore(store.state_root).read(manifest['source_bundle_sha256'])
        audit = strict_json_object(files['audit.json'], 'source audit')
        candidate = build_candidate(manifest, audit, files)
        images = {row['layer_id']: files[row['image']['path']] for row in candidate['layers']}
        return candidate, audit, files['composite.png'], images
    except (PipelineRunError, ValueError, KeyError, TypeError, OSError) as exc:
        raise inputs.AnimatedSourceError('input_preparation_source_invalid') from exc


def publish_prepared_source(store, project_id, context, pose_path):
    from .input_preparation_sources_publish import publish_prepared_source as publish
    return publish(store, project_id, context, pose_path)
