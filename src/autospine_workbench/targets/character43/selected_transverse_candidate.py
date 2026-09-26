"""Queue adapter with immutable scope and compact, non-accepting diagnostics."""
from hashlib import sha256
import json

from ...automation.storage_io import canonical_bytes
from .limb_transverse_candidate import build as compensate
from .limb_transverse_scope import PROFILE, resolve


def summary(report, slot):
    correction = next(r for r in report['joint_corrections'] if r['slot'] == slot)
    blocker = correction['fixed_area_blocker']
    fixed = None
    if blocker is not None:
        failures = blocker['failures']
        fixed = dict(status=blocker['status'], observations=len(failures),
            triangles=len({r['triangle'] for r in failures}),
            worst=min(failures, key=lambda r:r['setup_ratio']) if failures else None)
    before = next(r for r in report['parent_geometry']['records'] if r['slot'] == slot)
    after = next(r for r in report['geometry']['records'] if r['slot'] == slot)
    metrics = ('min_area_ratio', 'max_area_ratio', 'max_edge_stretch', 'inversion_samples', 'failing_frame_count')
    changes = {k:dict(before=before[k], after=after[k]) for k in metrics}
    regressions = [k for k in metrics if (before[k]-after[k] if k == 'min_area_ratio'
                                         else after[k]-before[k]) > 1e-9]
    return dict(validation=correction['validation'], fixed_area_blocker=fixed,
        sample_count=report['sample_count'], geometry_passed=after['passed'],
        whole_character_passed=report['geometry']['passed'], metrics=changes, regressions=regressions,
        maximum_displacement_px=report['transverse']['maximum_displacement_px'][slot],
        maximum_interpolation_error_px=report['transverse']['maximum_interpolation_error_px'],
        authority='none', selected=False, runtime_status='not_evaluated', visual_status='not_reviewed')


def build(files, character, plan, on_progress=None):
    slot, animation = plan['slot'], plan['animation']
    frozen = {k:v for k,v in plan['transverse_repair'].items() if k != 'character_sha256'}
    if resolve(files, character, slot, animation) != frozen:
        raise ValueError('motion_transverse_scope_changed')
    output, report = compensate(files, [slot], animation, on_progress)
    compact = summary(report, slot)
    evidence = json.loads(output['motion-review.json'])
    if compact['fixed_area_blocker']:
        evidence['issues'].append(dict(stage='repair', reason_code='motion_transverse_fixed_area_diagnostic'))
    if compact['regressions']:
        evidence['issues'].append(dict(stage='repair', reason_code='motion_transverse_geometry_regression'))
    output['motion-review.json'] = canonical_bytes(evidence)
    output['motion-repair.json'] = canonical_bytes(dict(profile=PROFILE, slot=slot, animation=animation,
        declaration=plan['transverse_repair'], transverse_repair=compact,
        parent_geometry=report['parent_geometry'], geometry=report['geometry'],
        unchanged_other_channels=True, authority='none', selected=False,
        scope='same_grid_whole_character_samples_not_visual_acceptance'))
    manifest = json.loads(output['character-manifest.json'])
    manifest['files'] = {n:sha256(raw).hexdigest() for n,raw in output.items() if n != 'character-manifest.json'}
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, evidence, report['geometry']
