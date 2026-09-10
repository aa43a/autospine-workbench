"""Source-bound user routing preference; never a binding adoption decision."""
from .storage_io import directory, publish_document, read_document
from .pipeline_run import PipelineRunError
from ..project_authoring_transaction import project_authoring_transaction

CHOICES = ('ordinary', 'sleeves', 'undecided')


def suggest(project):
    layers = [l for l in project['resolved']['layers'] if not l.get('empty') and l.get('disposition') != 'exclude']
    explicit = [l for l in layers if 'sleeve' in (l.get('canonical_role', '') + ' ' + l.get('name', '')).lower() or '袖' in l.get('name', '')]
    valid = [l for l in explicit if l.get('bbox', {}).get('width', 0) > 0 and l.get('bbox', {}).get('height', 0) > 0]
    if valid:
        return 'sleeves', ['检测到袖装名称或语义，且有有效图层范围：' + '、'.join(l['name'] for l in valid),
                           '这是初步路线建议；手、袖口与垂布仍需在区域标注中区分。']
    arm = [l for l in layers if l.get('canonical_role') in ('body.hand', 'body.arm', 'wear.top') or 'handwear' in l.get('name', '').lower()]
    if arm:
        return 'undecided', ['当前手臂相关图层尚不能可靠区分裸臂、手套和袖布。',
                             '请根据素材选择普通绑定或袖装处理；handwear 标签不会自动判定为袖子。']
    return 'ordinary', ['暂未检测到明确袖装语义，建议先进入普通绑定；如素材含袖布，可主动选择袖装处理。']


class ProjectRoute:
    def __init__(self, projects):
        self.projects = projects
        self.root = projects.state_root / 'project-route-v1'

    def _saved(self, project):
        folder = self.root / project
        if not folder.exists():
            return None
        directory(folder)
        files = sorted(folder.glob('revision-*.json'))
        if not files:
            return None
        value = read_document(files[-1])
        if (value.get('schema') != 'autospine.project-route-choice/v1' or value.get('project_id') != project
            or value.get('choice') not in CHOICES or type(value.get('revision')) is not int
            or value['revision'] < 1 or value.get('authority') != 'none'
            or files[-1].name != f"revision-{value['revision']:012d}.json"):
            raise PipelineRunError('project_route_invalid')
        return value

    def get(self, project):
        with project_authoring_transaction(self.projects.state_root, project):
            source = self.projects.get_project(project)
            sha = source['resolved']['sha256']
            saved = self._saved(project)
            stale = bool(saved and saved['source_sha256'] != sha)
            recommendation, reasons = suggest(source)
            if stale:
                reasons.insert(0, '项目来源已变化，请重新确认处理路线。')
            return dict(project_id=project, source_sha256=sha, revision=saved['revision'] if saved else 0,
                        choice=saved['choice'] if saved and not stale else 'undecided', stale=stale,
                        recommendation=recommendation, reasons=reasons, authority='none')

    def save(self, project, body):
        if (set(body) != {'choice', 'expected_resolved_sha256', 'expected_revision'}
            or body['choice'] not in CHOICES or type(body['expected_revision']) is not int):
            raise PipelineRunError('project_route_request_invalid')
        with project_authoring_transaction(self.projects.state_root, project):
            current = self.get(project)
            if body['expected_revision'] != current['revision'] or body['expected_resolved_sha256'] != current['source_sha256']:
                raise PipelineRunError('project_route_source_conflict')
            value = dict(schema='autospine.project-route-choice/v1', project_id=project,
                         source_sha256=current['source_sha256'], revision=current['revision'] + 1,
                         choice=body['choice'], authority='none')
            folder = directory(self.root / project, create=True)
            if not publish_document(folder / f"revision-{value['revision']:012d}.json", value, staging=self.root / 'staging'):
                raise PipelineRunError('project_route_source_conflict')
            return self.get(project)
