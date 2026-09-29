"""Project-owned sleeve annotation state and exact candidate snapshots."""
import json
from .storage_io import directory, publish_document, read_document, canonical_bytes
from .animated_inputs import AnimatedSourceError, load_inputs
from .pipeline_run import PipelineRunError
from ..project_authoring_transaction import project_authoring_transaction
from ..benchmark.mesh_storage import publish_mesh_report, read_mesh_report
from ..asset.planning.sleeve_regions import validate
from ..resolved_project import canonical_sha256

KIND = 'project-component-partitions'


class SleeveOnboarding:
    def __init__(self, projects):
        self.projects = projects
        self.root = projects.state_root / 'sleeve-onboarding-v1'

    def _latest(self, project):
        folder = self.root / project
        if not folder.exists():
            return None
        directory(folder)
        files = sorted(folder.glob('revision-*.json'))
        value = read_document(files[-1]) if files else None
        if value and (value.get('schema') != 'autospine.sleeve-onboarding/v1'
                      or value.get('project_id') != project or value.get('authority') != 'none'
                      or type(value.get('revision')) is not int or value['revision'] < 1
                      or files[-1].name != f"revision-{value['revision']:012d}.json"
                      or type(value.get('saved')) is not bool):
            raise PipelineRunError('sleeve_onboarding_invalid')
        return value

    def status(self, project):
        with project_authoring_transaction(self.projects.state_root, project):
            sha = self.projects.get_project(project)['resolved']['sha256']
            value = self._latest(project)
            stale = bool(value and value['source_sha256'] != sha)
            if value and not stale:
                try:
                    with load_inputs(self.projects, project) as inputs:
                        stale = inputs.source_addresses != value['input_addresses']
                        inputs.assert_current()
                except AnimatedSourceError:
                    stale = True
            result = dict(project_id=project, source_sha256=sha, revision=value['revision'] if value else 0,
                        status='stale' if stale else 'ready' if value else 'needs_preparation',
                        can_build=bool(value and not stale and value['saved']), authority='none',
                        candidate_sha256=value['candidate_sha256'] if value and not stale else None,
                        review_url=f'/api/projects/{project}/automation/sleeves/annotation/view' if value and not stale else None)
            if value and not stale and value.get('transfer_sha256'):
                from .sleeve_annotation_transfer import summary
                receipt = self._transfer(value)
                if not value['saved']:
                    result['migration'] = summary(receipt)
            if value and not stale and value.get('saved_reuse_sha256'):
                self._saved_reuse(value)
                result['saved_labels_reused'] = True
            return result

    def _saved_reuse(self, value):
        from .sleeve_saved_reuse import reuse
        read = lambda sha: read_mesh_report(self.projects.state_root, KIND, sha)
        receipt = read(value['saved_reuse_sha256'])
        revision = receipt.get('previous_revision')
        if type(revision) is not int or not 0 < revision < value['revision']:
            raise PipelineRunError('sleeve_onboarding_invalid')
        previous = read_document(self.root/value['project_id']/f'revision-{revision:012d}.json')
        if previous.get('saved_reuse_sha256'):
            self._saved_reuse(previous)
        result = reuse(previous, read(previous['candidate_sha256']),
                       read(previous['draft_sha256']), read(value['candidate_sha256']), value['source_sha256'])
        if result is None or result[1] != receipt:
            raise PipelineRunError('sleeve_onboarding_invalid')
        # A later explicit save may change labels; the preserved revision itself
        # must still contain exactly the copied draft.
        if value.get('saved_reuse_revision') == value['revision'] and canonical_sha256(result[0]) != value['draft_sha256']:
            raise PipelineRunError('sleeve_onboarding_invalid')

    def _transfer(self, value):
        from .sleeve_annotation_transfer import check
        read = lambda sha: read_mesh_report(self.projects.state_root, KIND, sha)
        receipt = read(value['transfer_sha256'])
        candidate = read(value['candidate_sha256'])
        transferred = check(receipt, read(receipt['previous_candidate_sha256']),
                            read(receipt['previous_draft_sha256']), candidate)
        if not value['saved'] and canonical_sha256(transferred) != value['draft_sha256']:
            raise PipelineRunError('sleeve_onboarding_invalid')
        return receipt

    def _append(self, project, value):
        previous = self._latest(project)
        value = dict(value, schema='autospine.sleeve-onboarding/v1', project_id=project,
                     revision=(previous['revision'] if previous else 0) + 1, authority='none')
        folder = directory(self.root / project, create=True)
        if not publish_document(folder / f"revision-{value['revision']:012d}.json", value, staging=self.root / 'staging'):
            raise PipelineRunError('sleeve_annotation_conflict')
        return value

    def prepare(self, project, expected_resolved_sha256):
        from .sleeve_onboarding_source import build_inputs
        with project_authoring_transaction(self.projects.state_root, project):
            status = self.status(project)
            if status['source_sha256'] != expected_resolved_sha256:
                raise PipelineRunError('project_snapshot_stale')
            if status['status'] == 'ready':
                return status
            with load_inputs(self.projects, project) as inputs:
                source, candidate, draft, auxiliary = build_inputs(inputs, project)
                previous = self._latest(project)
                extra = {}
                saved = False
                if previous and (previous['saved'] or previous.get('transfer_sha256')):
                    if previous.get('saved_reuse_sha256'):
                        self._saved_reuse(previous)
                    if previous.get('transfer_sha256'):
                        self._transfer(previous)
                    from .sleeve_annotation_transfer import transfer
                    read = lambda key: read_mesh_report(self.projects.state_root, KIND, previous[key])
                    draft, receipt = transfer(read('candidate_sha256'), read('draft_sha256'), candidate)
                    extra['transfer_sha256'] = publish_mesh_report(self.projects.state_root, KIND, receipt)
                    from .sleeve_saved_reuse import reuse
                    retained = reuse(previous, read('candidate_sha256'), read('draft_sha256'),
                                     candidate, expected_resolved_sha256)
                    if retained:
                        draft, receipt = retained
                        saved = True
                        extra = dict(saved_reuse_sha256=publish_mesh_report(self.projects.state_root, KIND, receipt),
                                     saved_reuse_revision=previous['revision'] + 1)
                # Auxiliary provenance is stored as a complete replayable bundle.
                closure = dict(schema='autospine.sleeve-onboarding-closure/v1', documents=auxiliary,
                               source_sha256=canonical_sha256(source), authority='none', production_authorized=False)
                hashes = [publish_mesh_report(self.projects.state_root, KIND, d) for d in (source, candidate, draft, closure)]
                inputs.assert_current()
                self._append(project, dict(source_sha256=expected_resolved_sha256,
                    input_addresses=inputs.source_addresses, mesh_sha256=hashes[0], candidate_sha256=hashes[1],
                    draft_sha256=hashes[2], closure_sha256=hashes[3], saved=saved, **extra))
            return self.status(project)

    def read_current(self, project, require_saved=False):
        # Replay the source once for this read, under the same authoring lock as
        # saves. A status roundtrip used to replay it before replaying it again.
        with project_authoring_transaction(self.projects.state_root, project):
            value = self._latest(project)
            if (not value or require_saved and not value['saved'] or
                    value['source_sha256'] != self.projects.get_project(project)['resolved']['sha256']):
                raise PipelineRunError('sleeve_annotation_required')
            try:
                with load_inputs(self.projects, project) as inputs:
                    if inputs.source_addresses != value['input_addresses']:
                        raise PipelineRunError('sleeve_annotation_required')
                    if value.get('transfer_sha256') and not value['saved']:
                        self._transfer(value)
                    if value.get('saved_reuse_sha256'):
                        self._saved_reuse(value)
                    result = self._read_documents(value)
                    inputs.assert_current()
                    return result
            except AnimatedSourceError as exc:
                raise PipelineRunError('sleeve_annotation_required') from exc

    def _read_documents(self, value):
        read = lambda key: read_mesh_report(self.projects.state_root, KIND, value[key])
        source, candidate, draft = read('mesh_sha256'), read('candidate_sha256'), read('draft_sha256')
        closure = read('closure_sha256')
        if (candidate['source_sha256'] != canonical_sha256(source)
            or closure['source_sha256'] != canonical_sha256(source)
            or canonical_sha256(closure['documents']['plan']) != source['sources']['plan_sha256']):
            raise PipelineRunError('sleeve_onboarding_invalid')
        validate(draft, candidate)
        return value, source, candidate, draft

    def save(self, project, body):
        if set(body) != {'expected_resolved_sha256', 'expected_revision', 'draft'}:
            raise PipelineRunError('sleeve_annotation_request_invalid')
        with project_authoring_transaction(self.projects.state_root, project):
            value, source, candidate, _ = self.read_current(project)
            if type(body['expected_revision']) is not int or body['expected_resolved_sha256'] != value['source_sha256']:
                raise PipelineRunError('sleeve_annotation_conflict')
            extra={}
            if body['expected_revision'] != value['revision']:
                from .sleeve_stale_save import recover
                draft,receipt=recover(self.root,project,value,body,
                    lambda sha:read_mesh_report(self.projects.state_root,KIND,sha))
                extra['editor_save_recovery']=receipt
            else:
                draft = validate(body['draft'], candidate)
            with load_inputs(self.projects, project) as inputs:
                if inputs.source_addresses != value['input_addresses']:
                    raise PipelineRunError('sleeve_annotation_source_changed')
                inputs.assert_current()
                digest = publish_mesh_report(self.projects.state_root, KIND, draft)
                self._append(project, dict(value, draft_sha256=digest, saved=True, **extra))
            return self.status(project)

    def page(self, project):
        from ..asset.planning.sleeve_region_review import render
        with project_authoring_transaction(self.projects.state_root, project):
            value, source, candidate, draft = self.read_current(project)
            with load_inputs(self.projects, project) as inputs:
                if inputs.source_addresses != value['input_addresses']:
                    raise PipelineRunError('sleeve_annotation_source_changed')
                html = render(candidate, draft, inputs, source)
                inputs.assert_current()
            endpoint = f'/api/projects/{project}/automation/sleeves/annotation/save'
            config = json.dumps(dict(endpoint=endpoint, revision=value['revision'], sha=value['source_sha256'])).replace('<', '\\u003c')
            bridge = '''const projectSave = CONFIG;
const originalMount = mountSleeveReview;
mountSleeveReview = (...args) => originalMount(...args, {onSave: async draft => {
 const response = await fetch(projectSave.endpoint, {method:'POST', headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},
 body:JSON.stringify({expected_revision:projectSave.revision,expected_resolved_sha256:projectSave.sha,draft})});
 const result = await response.json(); if (!response.ok) throw Error('保存失败，请刷新检查来源或版本冲突：'+(result.reason_code||response.status));
 projectSave.revision=result.revision;
}});
'''.replace('CONFIG', config)
            return html.replace('\nmountSleeveReview(document,', '\n' + bridge + '\nmountSleeveReview(document,').encode('utf-8')
