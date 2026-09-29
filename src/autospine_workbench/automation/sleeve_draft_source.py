"""Prefer project-owned saved annotations while retaining legacy exact inputs."""
from .sleeve_onboarding import SleeveOnboarding
from .storage_io import canonical_bytes
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
    _, _, _, draft = service.read_current(project, require_saved=True)
    return canonical_bytes(draft)
