"""Capture a real hard pose and compare exact solver output to a Git revision."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import random
import subprocess
import time
from unittest.mock import patch

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_ankle_policy import prepare as ankles
from autospine_workbench.automation.motion_pose_policy import prepare_inputs
from autospine_workbench.automation.motion_target_worker import build_candidate
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.area_projection import project


class Captured(Exception):
    pass


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    source = subprocess.check_output(['git', 'show', args.revision+':src/autospine_workbench/targets/character43/area_projection.py'], text=True)
    scope = {'__name__': 'autospine_workbench.targets.character43.benchmark_baseline',
             '__package__': 'autospine_workbench.targets.character43'}
    exec(compile(source, '<baseline>', 'exec'), scope)
    captured = {}

    def intercept(context, base, **kwargs):
        result = project(context, base, **kwargs)
        if result[1]['iterations'] == 1536:
            captured.update(context=deepcopy(context), base=base, kwargs=kwargs)
            raise Captured()
        return result

    request = json.loads(args.request.read_bytes())
    if request.get('clip') or request.get('torso_projection_profile'):
        raise ValueError('benchmark_requires_unclipped_default_torso_request')
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(args.state).load(identity['clip_sha256'], identity['bundle_sha256'])
    motion, view, fitted = prepare_inputs(bundle, request)
    kimodo = (bundle.raw_npz, bundle.kimodo_source) if bundle.source_kind == 'kimodo_npz' else None
    try:
        with patch('autospine_workbench.targets.character43.area_projection.project', intercept):
            build_candidate(AnimatedStore(args.state).read(request['character_sha256']), motion,
                None if kimodo else parse_bvh(bundle.raw_bvh), bundle.kimodo_map if kimodo else bundle.bvh_map,
                kimodo=kimodo, character_digest=request['character_sha256'], motion_digest=bundle.bundle_sha256,
                contact_correction=request.get('contact_correction', True),
                inferred_contact_profile=request.get('inferred_contact_profile'),
                depth_review_profile=request.get('depth_review_profile'), oblique=view, pose_fit=fitted,
                moving_ankles=ankles(bundle, request), layer_edits=request.get('layer_edits'),
                on_stage=lambda stage: print(stage, flush=True))
    except Captured:
        pass
    if not captured:
        raise RuntimeError('no_hard_pose_captured')
    (args.output/'pose.json').write_text(json.dumps(captured), encoding='utf-8')
    timings = {}
    outputs = {}
    for label, fn in [('baseline', scope['project']), ('active', project)]:
        start = time.perf_counter()
        outputs[label] = fn(captured['context'], captured['base'], **captured['kwargs'])
        timings[label] = time.perf_counter()-start
    context = captured['context']
    report = dict(timings_seconds=timings, speedup=timings['baseline']/timings['active'],
                  exactly_equal=outputs['baseline']==outputs['active'],
                  vertices=len(context['free']), free_vertices=sum(context['free']),
                  triangles=len(context['row']['triangles']),
                  active_triangles=sum(any(context['free'][i] for i in t) for t in context['row']['triangles']))
    rng = random.Random(29)
    for i in range(12):
        ctx, base, kwargs = deepcopy(context), deepcopy(captured['base']), deepcopy(captured['kwargs'])
        if i % 3 == 0:
            ctx['free'] = [rng.random() < .3 for _ in ctx['free']]
        elif i % 3 == 1:
            ctx['budget'] *= rng.uniform(.2, 1.2)
        else:
            for vertex in base:
                vertex[0] += rng.uniform(-.02, .02)
                vertex[1] += rng.uniform(-.02, .02)
        if project(ctx, base, **kwargs) != scope['project'](ctx, base, **kwargs):
            raise RuntimeError('perturbed_pose_differential_failure:'+str(i))
    report['perturbed_differential_cases'] = 12
    (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)
    if not report['exactly_equal']:
        raise RuntimeError('differential_failure')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('state', 'request', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--revision', default='HEAD')
    run(parser.parse_args())
