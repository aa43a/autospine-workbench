"""Project-owned sleeve annotation state and exact candidate snapshots."""
import json
from .storage_io import directory, publish_document, read_document, canonical_bytes
from .animated_inputs import load_inputs
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
            return dict(project_id=project, source_sha256=sha, revision=value['revision'] if value else 0,
                        status='stale' if stale else 'ready' if value else 'needs_preparation',
                        can_build=bool(value and not stale and value['saved']), authority='none',
                        candidate_sha256=value['candidate_sha256'] if value and not stale else None,
                        review_url=f'/api/projects/{project}/automation/sleeves/annotation/view' if value and not stale else None)

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
                # Auxiliary provenance is stored as a complete replayable bundle.
                closure = dict(schema='autospine.sleeve-onboarding-closure/v1', documents=auxiliary,
                               source_sha256=canonical_sha256(source), authority='none', production_authorized=False)
                hashes = [publish_mesh_report(self.projects.state_root, KIND, d) for d in (source, candidate, draft, closure)]
                inputs.assert_current()
                self._append(project, dict(source_sha256=expected_resolved_sha256,
                    input_addresses=inputs.source_addresses, mesh_sha256=hashes[0], candidate_sha256=hashes[1],
                    draft_sha256=hashes[2], closure_sha256=hashes[3], saved=False))
            return self.status(project)

    def read_current(self, project, require_saved=False):
        status = self.status(project)
        if status['status'] != 'ready' or require_saved and not status['can_build']:
            raise PipelineRunError('sleeve_annotation_required')
        value = self._latest(project)
        read = lambda key: read_mesh_report(self.projects.state_root, KIND, value[key])
        source, candidate, draft = read('mesh_sha256'), read('candidate_sha256'), read('draft_sha256')
        closure = read('closure_sha256')
        if (candidate['source_sha256'] != canonical_sha256(source)
            or closure['source_sha256'] != canonical_sha256(source)
            or canonical_sha256(closure['documents']['plan']) != source['sources']['plan_sha256']):
            raise PipelineRunError('sleeve_onboarding_invalid')
        validate(draft, candidate)
        with load_inputs(self.projects, project) as inputs:
            if inputs.source_addresses != value['input_addresses']:
                raise PipelineRunError('sleeve_annotation_source_changed')
            inputs.assert_current()
        return value, source, candidate, draft

    def save(self, project, body):
        if set(body) != {'expected_resolved_sha256', 'expected_revision', 'draft'}:
            raise PipelineRunError('sleeve_annotation_request_invalid')
        with project_authoring_transaction(self.projects.state_root, project):
            value, source, candidate, _ = self.read_current(project)
            if type(body['expected_revision']) is not int or body['expected_revision'] != value['revision'] or body['expected_resolved_sha256'] != value['source_sha256']:
                raise PipelineRunError('sleeve_annotation_conflict')
            draft = validate(body['draft'], candidate)
            with load_inputs(self.projects, project) as inputs:
                if inputs.source_addresses != value['input_addresses']:
                    raise PipelineRunError('sleeve_annotation_source_changed')
                inputs.assert_current()
                digest = publish_mesh_report(self.projects.state_root, KIND, draft)
                self._append(project, dict(value, draft_sha256=digest, saved=True))
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
