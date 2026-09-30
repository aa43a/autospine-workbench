"""Finite character recipes, separate from body animation and binding decisions."""
from .character_skirt_trial import PROFILE, TORSO_PROFILE, DRESS_PROFILE
from .pipeline_run import PipelineRunError
from .storage_io import read_document

SKIRT_PROFILES = (None, PROFILE, TORSO_PROFILE, DRESS_PROFILE)


def validate(options):
    if (type(options) is not dict or set(options) != {'skirt_profile'} or
            options.get('skirt_profile') not in SKIRT_PROFILES):
        raise PipelineRunError('production_character_options_invalid')


def launch_options(request):
    """Omission retains the historical CharacterJobs defaults."""
    if 'character_options' not in request:
        return {}
    options = request['character_options']
    validate(options)
    return dict(options)


def assert_selected(manager, project, job, options, *, verified=None):
    """Check the chosen job's recipe and executed trial, never edit its bindings."""
    validate(options)
    selected = verified if verified is not None else manager.verified_snapshot(project, job)[0]
    source = read_document(manager._path(job) / 'request.json')
    trial = selected.get('skirt_trial')
    actual = trial.get('profile') if isinstance(trial, dict) else None
    expected = options.get('skirt_profile')
    if source.get('skirt_profile') != expected or actual != expected:
        raise PipelineRunError('production_character_options_mismatch')


def assert_launch(request, launch):
    if 'character_options' not in request:
        return
    options = launch_options(request)
    if launch.get('skirt_profile') != options.get('skirt_profile'):
        raise PipelineRunError('production_character_options_mismatch')
