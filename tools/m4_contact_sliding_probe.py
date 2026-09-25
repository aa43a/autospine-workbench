"""Single-pose directional-guide trial, not confirmed garment ownership."""
import argparse
import json
from pathlib import Path
import numpy as np
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.contact_sliding_field import solve
from autospine_workbench.targets.character43.material_frontier_sliding import topology
from m4_pose_material_review import transfer


def run(sources, anchors_path, frontier_path, output):
    anchors=json.loads(anchors_path.read_bytes())['records']
    frontier=json.loads(frontier_path.read_bytes())['records']; rows=[]
    for i,(old,edge) in enumerate(zip(anchors,frontier,strict=True)):
        folder=sources/str(i); digest=json.loads((folder/'report.json').read_bytes())['candidate_bundle_sha256']
        if old['artifact_sha256']!=digest or edge['artifact_sha256']!=digest or old['character']!=edge['character']:
            raise ValueError('sliding_probe_identity_mismatch')
        doc=json.loads(AnimatedStore(folder/'isolated-store').read(digest)['skeleton.json'])
        arm,body=edge['arm'],edge['body'];meshes=doc['skins'][0]['attachments']
        am,bm=meshes[arm][arm],meshes[body][body]
        setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
        contour=np.asarray([s['world'] for s in edge['samples']]); graph=topology(edge['samples'])
        assignments={};unsupported=[]
        for v in old['original_supported_anchors']:
            p=np.asarray(setup[arm][v]); possibilities=[]
            for a,b in graph['edges']:
                delta=contour[b]-contour[a]; size=np.linalg.norm(delta)
                if size<1e-8:continue
                u=float(np.clip((p-contour[a])@delta/(size*size),0,1))
                possibilities.append((float(np.linalg.norm(p-(contour[a]+u*delta))),a,b,size))
            if not possibilities:unsupported.append(v);continue
            possibilities.sort();_,a,b,size=possibilities[0]
            direction=(contour[b]-contour[a])/size
            component=graph['components'][graph['labels'][a]]
            along=(contour[component]-p)@direction
            limits=[float(along.min()),float(along.max())]
            if not limits[0]<=0<=limits[1] or limits[1]-limits[0]<1e-8:
                unsupported.append(v);continue
            assignments[v]=dict(edge=[a,b],rest_length=float(size),limits=limits)
        row=dict(character=edge['character'],artifact_sha256=digest,assignments=assignments,
                 unsupported_vertices=unsupported,records=[],authority='none',selected=False,
                 scope='automatic_local_tangent_hypothesis_not_reviewed_contact_scope')
        for frame in edge['frames']:
            time=frame['time']; posed=sample(doc,'external-motion',time)[0]
            targets,ok=transfer(setup[body],posed[body],bm['triangles'],np.asarray(setup[arm])[list(assignments)])
            current,cv=transfer(setup[body],posed[body],bm['triangles'],contour)
            if not ok.all() or not cv.all():raise ValueError('sliding_probe_body_mapping_missing')
            guides={}
            for (v,item),target in zip(assignments.items(),targets):
                a,b=item['edge'];delta=current[b]-current[a];length=np.linalg.norm(delta)
                if length<1e-8:raise ValueError('sliding_probe_collapsed_guide')
                guides[v]=dict(origin=target.tolist(),tangent=(delta/length).tolist(),
                               limits=(np.asarray(item['limits'])*length/item['rest_length']).tolist())
            if not guides:
                row['records'].append(dict(time=time,status='no_supported_guides'));continue
            try:
                points,report=solve(setup[arm],posed[arm],np.asarray(am['triangles']).reshape(-1,3).tolist(),{},guides)
                row['records'].append(dict(time=time,**report,points=points))
            except ValueError as exc:
                row['records'].append(dict(time=time,status=str(exc)))
        rows.append(row)
    with output.open('x',encoding='utf8') as stream:json.dump(dict(selected=False,records=rows),stream,indent=2)
    print(json.dumps([dict(character=r['character'],guides=len(r['assignments']),unsupported=len(r['unsupported_vertices']),
        records=[dict(time=f['time'],status=f['status'],before_bad=len(f.get('before',{}).get('bad_triangles',[])),
        after_bad=len(f.get('after',{}).get('bad_triangles',[])),inversions=f.get('after',{}).get('inversions'),
        stretch=f.get('after',{}).get('max_edge_stretch')) for f in r['records']]) for r in rows]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('sources','anchors','frontier','output'):parser.add_argument(key,type=Path)
    args=parser.parse_args();run(args.sources,args.anchors,args.frontier,args.output)
