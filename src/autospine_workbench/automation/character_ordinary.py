"""Ordinary-route composition without inferring that ordinary means sleeveless."""
import json
from types import SimpleNamespace

from ..resolved_project import canonical_sha256
from ..targets.character43.ordinary_package import build_package
from .animated_input_index import inspect_registration, assert_registered_current
from .character_coverage_reader import read_job_coverage
from .pipeline_run import PipelineRunError
from .project_route import ProjectRoute


def route_source(projects, sleeves, project, resolved):
    saved = ProjectRoute(projects)._saved(project)
    if not saved or saved['source_sha256'] != resolved or saved['choice'] != 'ordinary':
        raise PipelineRunError('character_route_confirmation_required')
    # A failed/withdrawn repair is not permission to silently fall back to old weights.
    if sleeves.overview(project).get('job') is not None:
        raise PipelineRunError('character_sleeve_resolution_required')
    return canonical_sha256(saved)


def build_ordinary(application, sleeves, project, *, progress, cancel_requested):
    def check(stage):
        if cancel_requested(): raise PipelineRunError('character_build_canceled')
        progress(stage)
    check('resolve'); info=inspect_registration(application.projects,project)
    addresses=info['source_addresses'];resolved=addresses['resolved_project_sha256']
    route=route_source(application.projects,sleeves,project,resolved)
    check('base-preview')
    run=application.preview(project,resolved,'limb-flex-15',cancel_requested=cancel_requested)
    base=application.verified_files(project,run)
    if json.loads(base['preview-manifest.json'])['source_addresses']!=addresses:
        raise PipelineRunError('animated_input_changed')
    manager=SimpleNamespace(application=application,files=lambda *_:base,get=lambda *_:{'run':run})
    coverage=read_job_coverage(manager,project,'exact-run')['document']
    sources=dict(addresses,base_bundle_sha256=run['steps'][2]['outputs']['bundle_sha256'],route_choice_sha256=route)
    files=build_package(base,coverage,sources,checkpoint=lambda:check('compose'))
    from ..targets.character43.idle_package import append_idle
    files=append_idle(files,checkpoint=lambda:check('compose'))
    from .binding_provenance import attach_provenance
    files=attach_provenance(files,application.projects,project,addresses)
    assert_registered_current(application.projects,project,addresses)
    if route_source(application.projects,sleeves,project,resolved)!=route:
        raise PipelineRunError('character_route_changed')
    check('publish');digest=application.store.publish(files)
    return dict(artifact_sha256=digest,manifest=json.loads(application.store.read(digest)['character-manifest.json']))
