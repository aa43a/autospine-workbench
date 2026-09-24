"""Explicit source registration for project-level animated candidate previews.

Registrations grant no approval. Benchmark readers replay the full source closure;
the authoring checkpoint prevents a preview from ignoring newer workbench edits.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Callable

from ..benchmark.mesh_candidate_cli import inputs as replay_inputs
from ..benchmark.validation import validate_benchmark_manifest
from ..manifest_artifacts import require_safe_token, require_sha256
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from ..project_asset_resolution import layers as layer_assets
from ..project_authoring_transaction import project_authoring_transaction
from .project_snapshot import _read
from .storage_io import directory, publish_document, read_document


class AnimatedSourceError(ValueError):
    def __init__(self, reason_code):
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class AnimatedInputs:
    candidate: dict
    assisted: dict
    skeleton: dict
    bindings: dict
    draft: dict
    images: dict
    composite: bytes
    source_addresses: dict
    assert_current: Callable[[], None]


def _folder(store, project_id, *, create=False):
    require_safe_token(project_id, 'Project id')
    return directory(Path(store.state_root) / 'animation-inputs' / project_id, create=create)


def _checkpoint(store, project_id):
    project, _, key = _read(store, project_id)
    return project, {
        'resolved_project_sha256': key.resolved_project_sha256,
        'input_identity_sha256': key.input_identity_sha256,
    }


def _replay(store, registration):
    if registration.get('source_kind') == 'project_audit':
        from .input_preparation_sources_publish import replay_project_source
        return replay_project_source(store, registration)
    return replay_inputs(store.state_root, registration['manifest'],
                         registration['source_draft_sha256'], store.workspace_root)


def _match_audit(store, project_id, candidate):
    # The source snapshot includes ordering, visibility, offsets and all layer
    # references; matching only names or the PSD hash would be insufficient.
    record = store._record(project_id)
    if canonical_sha256(record.audit) != candidate['audit_snapshot_sha256']:
        raise AnimatedSourceError('animated_source_mismatch')
    project = store.get_project(project_id)
    layers = project['layers']
    if len(layers) != len(candidate['layers']):
        raise AnimatedSourceError('animated_source_mismatch')
    assets=layer_assets(store,project_id,[layer['id'] for layer in layers])
    for layer, source in zip(layers, candidate['layers']):
        if layer['source_index'] != source['traversal_index'] or layer['name'] != source['name']:
            raise AnimatedSourceError('animated_source_mismatch')
        raw = read_real_file(assets[layer['id']],
                             128 << 20, 'project layer')
        if hashlib.sha256(raw).hexdigest() != source['image_sha256']:
            raise AnimatedSourceError('animated_source_mismatch')


def register_inputs(store, project_id, manifest, draft_sha256):
    """Register one explicit, fully replayable selection for an unedited project."""
    try:
        require_sha256(draft_sha256, 'Binding draft')
        manifest = validate_benchmark_manifest(manifest)
        project, checkpoint = _checkpoint(store, project_id)
        if type(project['overrides']['revision']) is not int or project['overrides']['revision'] != 0:
            raise AnimatedSourceError('animated_source_rebase_required')
        registration = dict(schema='autospine.animated-input-registration/v1',
                            authority='none', production_authorized=False,
                            project_id=project_id, manifest=manifest,
                            source_draft_sha256=draft_sha256, checkpoint=checkpoint,
                            revision=0, previous_sha256=None)
        candidate, *_ = _replay(store, registration)
        _match_audit(store, project_id, candidate)
        if _checkpoint(store, project_id)[1] != checkpoint:
            raise AnimatedSourceError('animated_source_stale')
        folder = _folder(store, project_id, create=True)
        digest = canonical_sha256(registration)
        path = folder / '000000.json'
        publish_document(path, registration, staging=folder / 'staging')
        if read_document(path) != registration:
            raise AnimatedSourceError('animated_source_invalid')
        return digest
    except AnimatedSourceError:
        raise
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise AnimatedSourceError('animated_source_invalid') from exc


def _registrations(store, project_id):
    from .animated_registration import validate_entry
    path = Path(store.state_root) / 'animation-inputs' / project_id
    require_safe_token(project_id, 'Project id')
    if not path.exists():
        raise AnimatedSourceError('animated_source_missing')
    result = []
    for path in sorted(_folder(store, project_id).glob('*.json')):
        doc = read_document(path)
        if path.name != f'{len(result):06d}.json':
            raise AnimatedSourceError('animated_source_invalid')
        validate_entry(doc, project_id, len(result), result[-1] if result else None)
        result.append((canonical_sha256(doc), doc))
        if len(result) > 256:
            raise AnimatedSourceError('animated_source_invalid')
    if not result:
        raise AnimatedSourceError('animated_source_missing')
    return result


@contextmanager
def load_inputs(store, project_id):
    """Yield an exact candidate source, rejecting ambiguity and authoring drift."""
    try:
        _, checkpoint = _checkpoint(store, project_id)
        registrations = _registrations(store, project_id)
        digest, registration = registrations[-1]
        if registration['checkpoint'] != checkpoint:
            raise AnimatedSourceError('animated_source_stale')
        candidate, assisted, skeleton, bindings, draft, composite, images = _replay(store, registration)
        _match_audit(store, project_id, candidate)

        def assert_current():
            if _checkpoint(store, project_id)[1] != checkpoint:
                raise AnimatedSourceError('animated_source_stale')
            current = _registrations(store, project_id)
            if current[-1][0] != digest:
                raise AnimatedSourceError('animated_source_stale')

        from .animated_input_index import source_addresses
        addresses = source_addresses(checkpoint, digest, registration, canonical_sha256(candidate),
                                     canonical_sha256(skeleton), canonical_sha256(bindings),
                                     canonical_sha256(draft))
        assert_current()
    except AnimatedSourceError:
        raise
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise AnimatedSourceError('animated_source_invalid') from exc
    yield AnimatedInputs(candidate, assisted, skeleton, bindings, draft, images,
                         composite, addresses, assert_current)
    assert_current()


def save_binding_review(store, project_id, expected_input_sha256, records):
    """CAS append a reversible explicit user selection; no production approval."""
    from copy import deepcopy
    from ..benchmark.artifacts import publish_report
    from ..benchmark.layer_binding_draft import validate_layer_binding_draft
    from .animated_input_index import inspect_registration, assert_registered_current
    with project_authoring_transaction(store.state_root, project_id):
        # Saving an explicit selection performs no compilation or adoption. The
        # next build still replays all source analysis before producing assets.
        source = inspect_registration(store, project_id)
        addresses = source['source_addresses']
        if addresses['input_identity_sha256'] != expected_input_sha256:
            raise AnimatedSourceError('animated_review_conflict')
        expected_registration = addresses['animated_registration_sha256']
        draft = deepcopy(source['draft'])
        draft['records'] = deepcopy(records)
        try:
            draft = validate_layer_binding_draft(source['bindings'], draft)
        except (TypeError, ValueError) as exc:
            raise AnimatedSourceError('animated_binding_review_invalid') from exc
        assert_registered_current(store, project_id, addresses)
        before_sha, before = _registrations(store, project_id)[-1]
        if before_sha != expected_registration:
            raise AnimatedSourceError('animated_review_conflict')
        if draft == source['draft']:
            return expected_input_sha256
        if before['revision'] >= 255:
            raise AnimatedSourceError('animated_review_history_limit')
        draft_sha = publish_report(store.state_root, before['manifest']['dataset_id'],
                                   'layer-binding-drafts-v2', draft)
        after = dict(before, source_draft_sha256=draft_sha,
                     revision=before['revision'] + 1, previous_sha256=before_sha)
        folder = _folder(store, project_id)
        path = folder / f"{after['revision']:06d}.json"
        if not publish_document(path, after, staging=folder / 'staging'):
            raise AnimatedSourceError('animated_review_conflict')
        if read_document(path) != after:
            raise AnimatedSourceError('animated_source_invalid')
        return canonical_sha256({'project_checkpoint': after['checkpoint'],
                                 'registration_sha256': canonical_sha256(after)})
