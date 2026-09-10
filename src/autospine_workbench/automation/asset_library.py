"""Reversible catalog metadata, separate from source and certification identity."""
from copy import deepcopy
from .storage_io import directory, read_document, publish_document
from .pipeline_run import PipelineRunError
from ..project_authoring_transaction import project_authoring_transaction


class AssetLibrary:
    def __init__(self, projects):
        self.projects = projects
        self.root = projects.state_root / 'asset-library-v1'

    def metadata(self, project):
        with project_authoring_transaction(self.projects.state_root, project):
            folder = self.root / project
            if not folder.exists():
                return dict(revision=0, lifecycle='active', name=None)
            directory(folder)
            revisions = sorted(folder.glob('revision-*.json'))
            if not revisions:
                return dict(revision=0, lifecycle='active', name=None)
            value = read_document(revisions[-1])
            if (value.get('schema') != 'autospine.asset-library-entry/v1'
                or value.get('authority') != 'none' or value.get('project_id') != project
                or type(value.get('revision')) is not int or value['revision'] < 1
                or revisions[-1].name != f"revision-{value['revision']:012d}.json"
                or value.get('lifecycle') not in ('active', 'archived', 'trashed')
                or value.get('restore_lifecycle', 'active') not in ('active', 'archived')
                or (value.get('name') is not None and (not isinstance(value['name'], str) or not value['name'].strip()))):
                raise PipelineRunError('asset_metadata_invalid')
            return value

    def list(self):
        result = []
        for project in self.projects.list_projects():
            meta = self.metadata(project['id'])
            result.append({**project, 'project_revision': project['revision'],
                           'revision': meta['revision'], 'lifecycle': meta['lifecycle'],
                           'name': meta['name'] or project['name']})
        return result

    def change(self, project, body):
        action = body.get('action')
        keys = {'action', 'expected_revision'} | ({'name'} if action == 'rename' else set())
        if set(body) != keys or action not in ('rename', 'archive', 'trash', 'restore'):
            raise PipelineRunError('asset_request_invalid')
        if type(body['expected_revision']) is not int or body['expected_revision'] < 0:
            raise PipelineRunError('asset_request_invalid')
        with project_authoring_transaction(self.projects.state_root, project):
            self.projects.get_project(project)
            previous = self.metadata(project)
            if previous['revision'] != body['expected_revision']:
                raise PipelineRunError('asset_revision_conflict')
            value = deepcopy(previous)
            if action == 'rename':
                name = body['name']
                if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 for c in name):
                    raise PipelineRunError('asset_name_invalid')
                value['name'] = name.strip()
            elif action == 'archive':
                if value['lifecycle'] != 'active':
                    raise PipelineRunError('asset_state_conflict')
                value['lifecycle'] = 'archived'
            elif action == 'trash':
                if value['lifecycle'] == 'trashed':
                    raise PipelineRunError('asset_state_conflict')
                value['restore_lifecycle'] = value['lifecycle']
                value['lifecycle'] = 'trashed'
            else:
                if value['lifecycle'] == 'active':
                    raise PipelineRunError('asset_state_conflict')
                value['lifecycle'] = value.pop('restore_lifecycle', 'active') if value['lifecycle'] == 'trashed' else 'active'
            value.update(schema='autospine.asset-library-entry/v1', project_id=project,
                         revision=previous['revision'] + 1, authority='none')
            folder = directory(self.root / project, create=True)
            if not publish_document(folder / f"revision-{value['revision']:012d}.json", value, staging=self.root / 'staging'):
                raise PipelineRunError('asset_revision_conflict')
            return value
