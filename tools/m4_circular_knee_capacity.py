"""Measure a new knee representation's capacity before synthesizing a mesh."""
import argparse
import base64
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image
from m4_pose_material_review import transfer, alpha_at
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.circular_bend_capacity import inspect, nonuniform_area_bound
from autospine_workbench.targets.character43.pose_geometry_patch import _times


def section_width(points, triangles, center, axis):
    hits = []
    for start in range(0, len(triangles), 3):
        tri = triangles[start:start+3]
        for i, j in zip(tri, tri[1:]+tri[:1]):
            p, q = points[i], points[j]
            s = sum((p[k]-center[k])*axis[k] for k in range(2))
            t = sum((q[k]-center[k])*axis[k] for k in range(2))
            if s*t > 0 or abs(s-t) < 1e-10:
                continue
            f = s/(s-t)
            hit = [p[k]+f*(q[k]-p[k])-center[k] for k in range(2)]
            hits.append(abs(-axis[1]*hit[0]+axis[0]*hit[1]))
    if not hits or max(hits) <= 0:
        raise ValueError('circular_knee_section_missing')
    return max(hits)


def run(source, output):
    scene = json.loads(source.read_bytes())
    doc = scene['skeleton']
    animation = 'external-motion'
    rest_doc = deepcopy(doc)
    rest_doc['animations'] = {'setup': {}}
    rest = matrices(rest_doc, 'setup', 0)
    setup = sample_active(rest_doc, 'setup', 0)
    specs = []
    # Explicit slot/bone correspondence for this diagnostic fixture only.
    for slot, side in [('layer-003', 'r'), ('layer-004', 'l')]:
        hip, knee, ankle = [rest[n+'_'+side][4:] for n in ('thigh', 'calf', 'foot')]
        length = math.dist(hip, knee)
        axis = [(knee[i]-hip[i])/length for i in range(2)]
        name = setup['attachments'][slot]
        mesh = doc['skins'][0]['attachments'][slot][name]
        width = section_width(setup['vertices'][slot], mesh['triangles'], knee, axis)
        path = mesh.get('path', name)+'.png'
        # Mesh UVs address the unpadded region, not its padded atlas page.
        image = scene['textures'].get('images/'+path)
        if not isinstance(image, str) or not image.startswith('data:image/png;base64,'):
            raise ValueError('circular_knee_texture_identity')
        raw = base64.b64decode(image.split(',', 1)[1], validate=True)
        alpha = np.asarray(Image.open(BytesIO(raw)).convert('RGBA'))[:, :, 3]
        offsets = np.linspace(-width, width, math.ceil(2*width/.25)+1)
        points = np.asarray(knee)+offsets[:, None]*np.array([-axis[1], axis[0]])
        uv, covered = transfer(setup['vertices'][slot], np.asarray(mesh['uvs']).reshape(-1, 2), mesh['triangles'], points)
        values = alpha_at(alpha, uv)
        widths = [('mesh', width)]
        for threshold in (8, 128):
            supported = np.abs(offsets[covered & (values>=threshold)])
            if not len(supported):
                raise ValueError('circular_knee_alpha_section_missing')
            widths.append(('alpha_'+str(threshold), float(supported.max())))
        for mode, measured in widths:
            specs.append(dict(slot=slot, side=side, width_mode=mode, half_width=measured,
                              texture_sha256=sha256(raw).hexdigest(), section_step_max_px=.25,
                              mesh_sha256=canonical_sha256(mesh),
                              rest_length=length+math.dist(knee, ankle)))
    times = sorted({0., *_times(doc['animations'][animation].get('bones', {}))})
    times = sorted(set(times) | {(a+b)/2 for a, b in zip(times, times[1:])})
    rows = []
    for time in times:
        pose = matrices(doc, animation, time)
        for spec in specs:
            points = [pose[n+'_'+spec['side']][4:] for n in ('thigh', 'calf', 'foot')]
            rows.append(dict(time=time, slot=spec['slot'], width_mode=spec['width_mode'],
                             nonuniform=nonuniform_area_bound(*points, spec['half_width'], spec['rest_length']), **inspect(
                *points, spec['half_width'], spec['rest_length'])))
    report = dict(profile='circular-knee-capacity-v1', source_sha256=canonical_sha256(doc),
                  animation=animation, specs=specs, records=rows, selected=False, authority='none',
                  limitations=['alpha_width_sampled_at_setup_knee_section_only',
                               'uniform_material_arclength_is_a_hypothesis',
                               'model_failure_is_not_general_impossibility',
                               'inner_area_only_not_complete_geometry_or_render_acceptance'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(json.dumps(dict(samples=len(times), specs=specs,
                         passes=sum(r['meets_inner_area'] for r in rows), records=len(rows),
                         worst=[min((r for r in rows if r['slot']==s['slot'] and r['width_mode']==s['width_mode']),
                                    key=lambda r:r.get('maximum_inner_area_factor', 0)) for s in specs])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run(args.source, args.output)
