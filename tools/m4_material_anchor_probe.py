"""Three-structure key-pose test of setup-occluded shoulder material anchors."""
import argparse
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.material_anchor_field import solve
from autospine_workbench.targets.character43.material_anchor_constraints import inspect_paths
from autospine_workbench.asset.planning.component_local_solver import metrics
from m4_pose_material_review import transfer, alpha_at


def key_times(value):
    if isinstance(value,dict):
        return [v for k,v in value.items() if k=='time']+[t for k,v in value.items() if k!='time' for t in key_times(v)]
    if isinstance(value,list):return [t for item in value for t in key_times(item)]
    return []


def boundary_anchors(flat, eligible):
    """Topological perimeter only; this is not a semantic seam classifier."""
    if not flat or len(flat)%3:raise ValueError('anchor_boundary_triangles')
    edges=Counter()
    for i in range(0,len(flat),3):
        t=flat[i:i+3]
        if len(set(t))!=3:raise ValueError('anchor_boundary_triangles')
        edges.update(tuple(sorted((a,b))) for a,b in zip(t,t[1:]+t[:1]))
    if any(count>2 for count in edges.values()):raise ValueError('anchor_boundary_nonmanifold')
    perimeter={v for edge,count in edges.items() if count==1 for v in edge}
    return [v for v in eligible if v in perimeter]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('sources',type=Path);parser.add_argument('fields',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--boundary-only',action='store_true')
    args=parser.parse_args(); records=[]
    for index,name in enumerate(('alice','huiye','hongmeiling')):
        source=args.sources/str(index)
        receipt=json.loads((source/'report.json').read_bytes())
        field=json.loads((args.fields/(name+'.json')).read_bytes())
        artifact=receipt['candidate_bundle_sha256']
        if field['candidate']!=artifact:raise ValueError('anchor_probe_identity_mismatch')
        files=AnimatedStore(source/'isolated-store').read(artifact)
        doc=json.loads(files['skeleton.json']); animation='external-motion'
        arm,body=field['arm'],field['body']
        setup,pose=sample(dict(doc,animations={'setup':{}}),'setup',0)
        meshes=doc['skins'][0]['attachments']; mesh=meshes[arm][arm]; torso=meshes[body][body]
        texture=lambda m,slot:np.asarray(Image.open(BytesIO(files['images/'+m.get('path',slot)+'.png'])).convert('RGBA'))[:,:,3]
        body_uv,covered=transfer(setup[body],np.asarray(torso['uvs']).reshape(-1,2),torso['triangles'],np.asarray(setup[arm]))
        root=np.array(pose['upperarm_r'][:2]);length=np.linalg.norm(np.array(pose['forearm_r'][:2])-root)
        distance=np.linalg.norm(np.asarray(setup[arm])-root,axis=1)
        supported=covered & (alpha_at(texture(torso,body),body_uv)>=254) & (alpha_at(texture(mesh,arm),np.asarray(mesh['uvs']).reshape(-1,2))>=8)
        anchors=np.flatnonzero(supported & (distance<=.65*length)).tolist()
        supported_anchors=anchors[:]
        if args.boundary_only:anchors=boundary_anchors(mesh['triangles'],anchors)
        movable=np.flatnonzero(distance<=length).tolist()
        row=dict(character=name,artifact_sha256=artifact,arm=arm,body=body,anchors=anchors,movable=movable,
                 hypothesis=('occluded_proximal_boundary_follows_body' if args.boundary_only else
                             'occluded_proximal_material_follows_body_with_one_arm_length_support'),
                 original_supported_anchors=supported_anchors,
                 anchor_radius_px=float(.65*length),movable_radius_px=float(length),records=[])
        if not anchors:
            row['status']='no_vertex_anchor_support';records.append(row);continue
        flat=mesh['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
        duration=max(key_times(doc['animations'][animation]))
        for time in (0.,duration*.43125,duration):
            before=sample(doc,animation,time)[0]
            targets,valid=transfer(setup[body],before[body],torso['triangles'],np.asarray(setup[arm])[anchors])
            if not valid.all():raise ValueError('anchor_probe_body_correspondence_missing')
            fixed=dict(zip(anchors,targets.tolist()))
            constraints=inspect_paths(setup[arm],before[arm],triangles,fixed,movable)
            after,evidence=solve(setup[arm],before[arm],triangles,fixed,movable)
            row['records'].append(dict(time=time,before=metrics(setup[arm],before[arm],triangles),
                after=metrics(setup[arm],after,triangles),solver=evidence,constraints=constraints,points=after))
        row['status']='rejected_geometry' if any(x['after']['inversions'] or x['after']['bad_triangles'] or
            x['after']['max_edge_stretch']>2 for x in row['records']) else 'key_pose_only_unverified'
        records.append(row)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(dict(authority='none',selected=False,records=records),stream,indent=2)
    print(json.dumps([dict(character=r['character'],anchors=len(r['anchors']),records=[dict(time=x['time'],
        before_inversions=x['before']['inversions'],after_inversions=x['after']['inversions'],
        before_bad=len(x['before']['bad_triangles']),after_bad=len(x['after']['bad_triangles']),
        max_stretch=x['after']['max_edge_stretch'],displacement=x['solver']['maximum_displacement_px'])
        for x in r['records']]) for r in records]))


if __name__=='__main__':main()
