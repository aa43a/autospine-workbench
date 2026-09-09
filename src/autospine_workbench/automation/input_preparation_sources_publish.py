"""Publish a zero-reviewed assisted source after a real source-bound pose run."""
from pathlib import Path
from tempfile import TemporaryDirectory

from ..asset.joints.layer_binding import build_layer_bindings, validate_layer_bindings
from ..asset.joints.reviewed_skeleton import build_reviewed_skeleton, validate_reviewed_skeleton
from ..benchmark.artifacts import publish_report, read_report
from ..benchmark.assisted_joint_draft import build_assisted_joint_draft, validate_assisted_joint_draft
from ..benchmark.joint_baseline import build_joint_baseline, validate_joint_baseline
from ..benchmark.layer_binding_draft import build_layer_binding_draft, validate_layer_binding_draft
from ..benchmark.pose_source import ingest_pose, read_pose
from ..project_authoring_transaction import project_authoring_transaction
from ..resolved_project import canonical_sha256
from . import animated_inputs as inputs
from .input_preparation_sources import read_source
from .storage_io import canonical_bytes, directory, publish_document


def replay_project_source(store, registration):
    manifest = registration['manifest']
    candidate, audit, composite, images = read_source(store, manifest)
    dataset = manifest['dataset_id']
    read = lambda kind, sha: read_report(store.state_root, dataset, kind, sha)
    draft = read('layer-binding-drafts-v2', registration['source_draft_sha256'])
    bindings = read('layer-binding-candidates-v2', draft['source_bindings_sha256'])
    skeleton = read('assisted-skeleton-candidates', bindings['source_skeleton_sha256'])
    assisted = read('assisted-joint-drafts', skeleton['source_assisted_sha256'])
    baseline = read('joint-baselines', assisted['source_baseline_sha256'])
    validate_joint_baseline(candidate, audit, baseline)
    pose = read_pose(store.state_root, candidate, assisted['source_pose_sha256'])
    validate_assisted_joint_draft(candidate, baseline, pose, assisted)
    validate_reviewed_skeleton(candidate, assisted, skeleton)
    validate_layer_bindings(candidate, assisted, skeleton, bindings)
    validate_layer_binding_draft(bindings, draft)
    return candidate, assisted, skeleton, bindings, draft, composite, images


def publish_prepared_source(store, project_id, context, pose_path):
    with project_authoring_transaction(store.state_root, project_id):
        context.assert_current()
        if context.manifest['project_id'] != project_id:
            raise inputs.AnimatedSourceError('input_preparation_source_invalid')
        try:
            inputs._registrations(store, project_id)
        except inputs.AnimatedSourceError as exc:
            if exc.reason_code != 'animated_source_missing':
                raise
        else:
            raise inputs.AnimatedSourceError('input_preparation_already_registered')
        candidate, audit, _, _ = read_source(store, context.manifest)
        if candidate != context.candidate or audit != context.audit:
            raise inputs.AnimatedSourceError('input_preparation_source_invalid')
        staging = directory(Path(store.state_root) / 'input-preparation' / 'staging', create=True)
        with TemporaryDirectory(dir=staging) as temporary:
            if isinstance(pose_path, dict):
                path = Path(temporary) / 'pose.json'
                path.write_bytes(canonical_bytes(pose_path))
            else:
                path = Path(pose_path)
            pose = ingest_pose(store.state_root, candidate, path)
        baseline = build_joint_baseline(candidate, audit)
        assisted = build_assisted_joint_draft(candidate, baseline, pose)
        skeleton = build_reviewed_skeleton(candidate, assisted)
        bindings = build_layer_bindings(candidate, assisted, skeleton)
        draft = build_layer_binding_draft(bindings)
        dataset = context.manifest['dataset_id']
        envelope = dict(schema='autospine.benchmark-audit-snapshot/v1', authority='none', payload=audit)
        for kind, doc in [('semantic-audits', envelope), ('semantic-candidates', candidate),
                          ('joint-baselines', baseline), ('assisted-joint-drafts', assisted),
                          ('assisted-skeleton-candidates', skeleton), ('layer-binding-candidates-v2', bindings),
                          ('layer-binding-drafts-v2', draft)]:
            publish_report(store.state_root, dataset, kind, doc)
        registration = dict(schema='autospine.animated-input-registration/v3', source_kind='project_audit',
                            authority='none', production_authorized=False, project_id=project_id,
                            manifest=context.manifest, checkpoint=context.checkpoint,
                            source_draft_sha256=canonical_sha256(draft), revision=0, previous_sha256=None)
        replay_project_source(store, registration)
        context.assert_current()
        folder = inputs._folder(store, project_id, create=True)
        if not publish_document(folder / '000000.json', registration, staging=folder / 'staging'):
            raise inputs.AnimatedSourceError('input_preparation_already_registered')
        digest = inputs._registrations(store, project_id)[-1][0]
        return dict(registration_sha256=digest, input_identity_sha256=canonical_sha256(
            {'project_checkpoint': context.checkpoint, 'registration_sha256': digest}),
                    reviewed_joint_count=0, source_registered=True, skeleton_status=skeleton['status'],
                    reason_codes=skeleton['reason_codes'], authority='none', production_authorized=False)
