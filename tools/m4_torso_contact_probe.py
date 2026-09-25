"""Bounded reverse-contact trial: let proximal garment follow arm, not vice versa."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.material_anchor_field import solve
from autospine_workbench.asset.planning.component_local_solver import metrics
from m4_pose_material_review import transfer, alpha_at
from m4_material_anchor_probe import key_times


def subdivide(points, triangles):
    result = [list(p) for p in points]; mids = {}; output = []
    def mid(a, b):
        key = tuple(sorted((a, b)))
        if key not in mids:
            mids[key] = len(result)
            result.append(((np.asarray(points[a])+points[b])/2).tolist())
        return mids[key]
    for a, b, c in triangles:
        ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
        output.extend([[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]])
    return result, output


def run(sources, fields, output):
    rows = []
    for i, name in enumerate(('alice', 'huiye', 'hongmeiling')):
        folder = sources/str(i)
        digest = json.loads((folder/'report.json').read_bytes())['candidate_bundle_sha256']
        field = json.loads((fields/(name+'.json')).read_bytes())
        if field['candidate'] != digest: raise ValueError('torso_probe_identity_mismatch')
        files = AnimatedStore(folder/'isolated-store').read(digest)
        doc = json.loads(files['skeleton.json']); arm, body = field['arm'], field['body']
        am, bm = [doc['skins'][0]['attachments'][s][s] for s in (arm, body)]
        setup, bones = sample(dict(doc, animations={'setup': {}}), 'setup', 0)
        arm_tri = np.asarray(am['triangles']).reshape(-1, 3).tolist()
        distances = [np.linalg.norm(np.asarray(setup[arm][a])-setup[arm][b]) for t in arm_tri for a,b in zip(t,t[1:]+t[:1])]
        spacing = float(np.median(distances))
        points, tris = setup[body], np.asarray(bm['triangles']).reshape(-1, 3).tolist()
        rounds = 0
        while rounds < 5 and max(np.linalg.norm(np.asarray(points[a])-points[b]) for t in tris for a,b in zip(t,t[1:]+t[:1])) > spacing:
            points, tris = subdivide(points, tris); rounds += 1
        rest = np.asarray(points)
        root = np.asarray(bones['upperarm_r'][:2]); length = np.linalg.norm(np.asarray(bones['forearm_r'][:2])-root)
        distance = np.linalg.norm(rest-root, axis=1)
        auv, covered = transfer(setup[arm], np.asarray(am['uvs']).reshape(-1,2), am['triangles'], rest)
        buv, body_covered = transfer(setup[body], np.asarray(bm['uvs']).reshape(-1,2), bm['triangles'], rest)
        def alpha(mesh, slot):
            return np.asarray(Image.open(BytesIO(files['images/'+mesh.get('path',slot)+'.png'])).convert('RGBA'))[:,:,3]
        anchors = np.flatnonzero(covered & body_covered & (alpha_at(alpha(am,arm),auv)>=8)
                                & (alpha_at(alpha(bm,body),buv)>=254) & (distance<=.65*length)).tolist()
        movable = np.flatnonzero(distance<=length).tolist()
        row = dict(character=name, artifact_sha256=digest, original_body_vertices=len(setup[body]),
                   refined_vertices=len(points), subdivisions=rounds, spacing_reference_px=spacing,
                   anchors=len(anchors), movable=len(movable), records=[], authority='none', selected=False)
        if not anchors or len(movable)>256:
            row['status']='unsupported_anchor_or_solver_budget'; rows.append(row); continue
        duration = max(key_times(doc['animations']['external-motion']))
        for time in (0.,duration*.43125,duration):
            posed = sample(doc,'external-motion',time)[0]
            current, ok = transfer(setup[body],posed[body],bm['triangles'],rest)
            targets, valid = transfer(setup[arm],posed[arm],am['triangles'],rest[anchors])
            if not ok.all() or not valid.all(): raise ValueError('torso_probe_mapping_missing')
            corrected, evidence = solve(points,current.tolist(),tris,dict(zip(anchors,targets.tolist())),movable)
            before, after = metrics(points,current.tolist(),tris),metrics(points,corrected,tris)
            row['records'].append(dict(time=time,before=before,after=after,solver=evidence))
        row['status']='rejected_geometry' if any(r['after']['inversions'] or r['after']['bad_triangles'] or
            r['after']['max_edge_stretch']>2 for r in row['records']) else 'key_pose_only_unverified'
        rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x',encoding='utf8') as stream: json.dump(dict(records=rows,selected=False),stream,indent=2)
    print(json.dumps([dict(character=r['character'],vertices=r['refined_vertices'],anchors=r['anchors'],
        movable=r['movable'],status=r['status'],frames=[dict(time=f['time'],before_bad=len(f['before']['bad_triangles']),
        after_bad=len(f['after']['bad_triangles']),inversions=f['after']['inversions'],stretch=f['after']['max_edge_stretch']) for f in r['records']]) for r in rows]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('sources','fields','output'): parser.add_argument(key,type=Path)
    args=parser.parse_args(); run(args.sources,args.fields,args.output)
