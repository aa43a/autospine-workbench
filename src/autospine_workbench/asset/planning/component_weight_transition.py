"""Bounded alpha-width experiments for both limb joints; no automatic adoption."""
from copy import deepcopy
import hashlib
import math
from .component_mesh import SCHEMA as MESH_SCHEMA, isolated_png
from .component_partitions import validate as validate_partition
from ..joints.joint_plane_weights import _planes, _transition
from ..joints.partition_mesh_qa import evaluate
from ...resolved_project import canonical_sha256

SCHEMA = 'autospine.component-weight-transition/v1'
FACTORS = (1, 2, 4)


def _passes(p):
    return (p['inversions'] == 0 and p['min_area_ratio'] >= .5
            and p['max_area_ratio'] <= 2 and p['max_edge_stretch'] <= 2)


def _score(qa):
    return (sum(not _passes(p) for p in qa['probes']),
            sum(p['inversions'] for p in qa['probes']))


def measure(region, bbox, bones):
    evidence = []
    for index, (pivot, normal, old) in enumerate(_planes(bones)):
        radius, count = 0., 0
        for y, start, end in region['runs']:
            for x in range(start, end):
                delta = [bbox[0]+x+.5-pivot[0], bbox[1]+y+.5-pivot[1]]
                if abs(sum(delta[k]*normal[k] for k in (0,1))) <= 2*old:
                    radius = max(radius, abs(-delta[0]*normal[1]+delta[1]*normal[0]))
                    count += 1
        cap = .9*min(math.dist(b['head_xy'], b['tail_xy']) for b in bones[index:index+2])
        evidence.append(dict(joint_id=bones[index+1]['id'], sample_count=count,
                             transverse_radius=radius, original_halfwidth=old, cap=cap))
    return evidence


def reweight(mesh, bones, evidence, factor):
    if type(factor) is not int or factor not in FACTORS:
        raise ValueError('component_transition_factor_invalid')
    planes = _planes(bones)
    widths = [max(old, min(e['cap'], factor*e['transverse_radius'])) if e['sample_count'] else old
              for (_, _, old), e in zip(planes, evidence)]
    result = deepcopy(mesh)
    for vertex, weights in zip(result['vertices_xy'], result['weights']):
        values = [_transition(vertex, (p, n, width)) for (p,n,_), width in zip(planes, widths)]
        elbow, wrist = values
        for influence, value in zip(weights, [1-elbow, elbow*(1-wrist), elbow*wrist]):
            influence['weight'] = value
    result['qa'] = evaluate(result['vertices_xy'], result['triangles'], result['weights'], bones)
    passed = result['qa']['passed'] and not result['raster_qa']['uncovered_alpha_pixels']
    result['status'] = 'candidate_requires_review' if passed else 'blocked'
    result['reason_codes'] = ['experimental_local_transition', 'binding_not_adopted']
    if not passed: result['reason_codes'].append('partition_deformation_qa_failed')
    return result, widths


def build(baseline, skeleton, entries):
    if (baseline['schema'] != MESH_SCHEMA or baseline['authority'] != 'none'
            or baseline['production_authorized'] is not False
            or baseline['skeleton_sha256'] != canonical_sha256(skeleton)):
        raise ValueError('component_transition_source_mismatch')
    regions = {(layer['layer_id'], r['id']): (layer, r)
               for layer, _, candidate, _ in entries for r in candidate['components']}
    for layer, raw, candidate, _ in entries:
        validate_partition(layer, raw, candidate)
        for row in baseline['records']:
            if row['layer_id'] != layer['layer_id']: continue
            if row['source_image_sha256'] != hashlib.sha256(raw).hexdigest():
                raise ValueError('component_transition_texture_mismatch')
            if row['mesh']:
                region = regions[layer['layer_id'], row['component_id']][1]
                if row['isolated_image_sha256'] != hashlib.sha256(isolated_png(raw, region)).hexdigest():
                    raise ValueError('component_transition_mask_mismatch')
    bones = {b['id']: b for b in skeleton['bones']}
    records, comparisons = deepcopy(baseline['records']), []
    for row in records:
        mesh = row['mesh']
        if not mesh or not mesh['qa'] or len(mesh['bone_ids']) != 3:
            continue
        chain = [bones[b] for b in mesh['bone_ids']]
        layer, region = regions[row['layer_id'], row['component_id']]
        evidence = measure(region, layer['bbox'], chain)
        best, selected, trials = mesh, None, []
        for factor in FACTORS:
            trial, widths = reweight(mesh, chain, evidence, factor)
            regressions = [p['id'] for p, original in zip(trial['qa']['probes'], mesh['qa']['probes'])
                           if _passes(original) and not _passes(p)]
            trials.append(dict(factor=factor, halfwidths=widths, qa=trial['qa'], newly_failed_probes=regressions))
            score, previous = _score(trial['qa']), _score(best['qa'])
            if not regressions and score != previous and all(a <= b for a,b in zip(score, previous)):
                best, selected = trial, factor
        row.update(mesh=best, status=best['status'], reason_codes=best['reason_codes'])
        comparisons.append(dict(layer_id=row['layer_id'], component_id=row['component_id'],
                                baseline_qa=mesh['qa'], evidence=evidence, trials=trials,
                                selected_factor=selected, selected_qa=best['qa']))
    return dict(schema=SCHEMA, profile='component-alpha-width-both-joints-v1',
                project_id=baseline['project_id'], source_mesh_sha256=canonical_sha256(baseline),
                skeleton_sha256=canonical_sha256(skeleton), records=records, comparisons=comparisons,
                factors=list(FACTORS), authority='none', production_authorized=False,
                seam_status='not_evaluated', runtime_status='not_evaluated')
