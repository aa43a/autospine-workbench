"""Compare one-surface material transport with the unchanged motion candidate."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
from m4_squat_stage_players import stage
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.deform_addition import entries,local_delta,add
from autospine_workbench.targets.character43.material_transport_map import build,apply


def run(source,uv_source,pose_source,output):
    parent=json.loads((source/'report.json').read_bytes())['candidate_bundle_sha256']
    uv=json.loads((uv_source/'probe.json').read_bytes());pose=json.loads((pose_source/'probe.json').read_bytes())
    if uv['parent']!=parent or pose['parent']!=parent:raise ValueError('material_transport_parent')
    files=AnimatedStore(source/'isolated-store').read(parent)
    variant=AnimatedStore(uv_source/'uv/isolated-store').read(uv['candidate'])
    original=json.loads(files['skeleton.json']);doc=deepcopy(original);alternative=json.loads(variant['skeleton.json'])
    name='external-motion';times=[k['time'] for k in pose['records'][0]['alpha_keys']]
    cached=[(sample(original,name,t)[0],matrices(original,name,t)) for t in times]
    records=[]
    for record in pose['records']:
        slot=record['slot'];mesh=doc['skins'][0]['attachments'][slot][slot]
        mapped=alternative['skins'][0]['attachments'][slot][slot]
        mapping=build(mesh['uvs'],mapped['uvs'],mesh['triangles'],preserve_unmapped=True)
        owners=entries(mesh);corrections=[];peak=0.
        keys=record['alpha_keys']
        for time,(points,transforms) in zip(times,cached):
            blend=float(np.interp(time,[k['time'] for k in keys],[k['value'] for k in keys]))
            after=apply(points[slot],mapping,blend)
            peak=max(peak,float(np.max(np.linalg.norm(np.asarray(after)-points[slot],axis=1))))
            corrections.append(dict(time=time,vertices=local_delta(doc,owners,transforms,points[slot],after)))
        tracks=doc['animations'][name]['attachments']['default'][slot][slot]
        tracks['deform']=add(tracks.get('deform',[]),corrections,len(corrections[0]['vertices']))
        records.append(dict(slot=slot,maximum_world_displacement=peak,
                            extrapolated_vertices=mapping['extrapolated_vertices'],maximum_extrapolation=mapping['maximum_extrapolation'],
                            preserved_unmapped_vertices=mapping['preserved_unmapped_vertices']))
    if doc['skins']!=original['skins'] or doc['slots']!=original['slots'] or doc['bones']!=original['bones']:
        raise ValueError('material_transport_bind_changed')
    output.mkdir(parents=True,exist_ok=False)
    report=dict(parent=parent,records=records,authority='none',selected=False,profile='single-surface-material-transport-v1')
    (output/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    digest=stage(doc,files,times,output/'transport',parent)
    path=output/'transport/runtime/player-assets/scene.json';scene=json.loads(path.read_bytes())
    scene['info']=json.loads((source/'runtime/report.json').read_bytes())['info']
    path.write_text(json.dumps(scene),encoding='utf-8')
    report.update(candidate=digest,shared_camera=scene['info'])
    (output/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('source','uv_source','pose_source','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.source,a.uv_source,a.pose_source,a.output)
