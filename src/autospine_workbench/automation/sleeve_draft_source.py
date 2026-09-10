"""Prefer project-owned saved annotations while retaining legacy exact inputs."""
from .sleeve_onboarding import SleeveOnboarding
from .animated_inputs import load_inputs
from .storage_io import canonical_bytes
from .pipeline_run import PipelineRunError
from ..safe_input_files import read_real_file


def available(projects, legacy_root, project):
    service = SleeveOnboarding(projects)
    if service._latest(project):
        return service.status(project)['can_build']
    return (legacy_root / project / 'draft.json').is_file()


def read(projects, legacy_root, project):
    service = SleeveOnboarding(projects)
    if not service._latest(project):
        return read_real_file(legacy_root / project / 'draft.json', 16 << 20, 'sleeve draft')
    value, _, _, draft = service.read_current(project, require_saved=True)
    with load_inputs(projects, project) as inputs:
        if inputs.source_addresses != value['input_addresses']:
            raise PipelineRunError('sleeve_annotation_source_changed')
        inputs.assert_current()
    return canonical_bytes(draft)
