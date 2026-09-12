"""Opt-in texture trial; source decisions and layer completeness are unchanged."""
import json

from .pipeline_run import PipelineRunError

PROFILE = 'aligned-low-alpha-v1'


def validate(profile):
    if profile is not None and profile != PROFILE:
        raise PipelineRunError('character_texture_profile_invalid')


def apply_selected(manager, request, result):
    profile = request.get('residual_texture_profile')
    validate(profile)
    if profile is None:
        return result
    from ..targets.character43.residual_texture_transfer import build
    store = manager.application.store
    files, report = build(store.read(result['artifact_sha256']))
    manifest = json.loads(files['character-manifest.json'])
    return dict(artifact_sha256=store.publish(files), manifest=manifest,
                texture_trial=dict(profile=profile, source_artifact_sha256=result['artifact_sha256'],
                    transferred_pixels=sum(r['counts'].get('transferred', 0) for r in report['rows']),
                    authority='none'))
