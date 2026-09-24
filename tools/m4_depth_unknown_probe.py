"""Locate unknown depth triangles without changing a candidate or its gate."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import re
from pathlib import Path
from urllib.request import urlopen

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43 import local_depth_analysis as analysis
from autospine_workbench.targets.character43.sleeve_depth_intervals import at


def run(job, evidence_path, output):
    if not re.fullmatch(r'motion-[a-f0-9]{32}',job):raise ValueError('invalid_job')
    if output.exists():raise ValueError('output_exists')
    evidence_bytes=evidence_path.read_bytes();evidence=json.loads(evidence_bytes)
    if evidence.get('authority')!='none' or evidence.get('selected') is not False:
        raise ValueError('diagnostic_evidence_required')
    if not 1<=len(evidence.get('records',[]))<=66:raise ValueError('record_limit')
    with urlopen('http://127.0.0.1:8918/api/motions/'+job,timeout=60) as response:
        current=json.load(response)
    artifact=current['result']['artifact_sha256']
    if current['status']!='succeeded' or evidence['job_id']!=job or evidence['artifact_sha256']!=artifact:
        raise ValueError('candidate_identity_mismatch')
    root=Path('workspace');request=read_document(root/'jobs/motion-intake-v1'/job/'request.json')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    files=AnimatedStore(root).read(artifact)
    analysis.verify_source(files,artifact,bundle,request)
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    yaw=(request.get('projection') or {}).get('yaw_degrees',0)
    if bundle.source_kind=='kimodo_npz':
        sampler=analysis.KimodoDepthSampler(bundle.raw_npz,bundle.kimodo_source,mapping,yaw,
                                           interpolation='linear_observed_positions')
    else:
        sampler=analysis.SegmentDepthSampler(analysis.parse_bvh(bundle.raw_bvh),mapping,yaw)
    document=json.loads(files['skeleton.json'])
    receipt=json.loads(files.get('motion-torso-projection.json',b'{}'));options={}
    if receipt.get('applied'):
        options['plane_provider']=analysis.BakedWarpPlane(document,'external-motion',receipt,analysis.prepare(bundle,request))
    probe=analysis.Probe(document,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
    helpers=evidence['sleeve_helpers']
    checker=analysis.Checker(probe,sampler,pixelwise=True,sleeve_helpers=helpers,**options)
    rows=[]
    # Diagnose only recorded instants where every explicit helper plane existed.
    for record in evidence['records']:
        model=record['check'].get('sleeve_depth_model',{})
        if model.get('unavailable_helpers') or not model.get('helper_planes'):continue
        arm,body=record['pair'];time=record['check']['time'];tick=record['source_tick']
        triangles=Counter()
        def collect(index,counts):
            if counts.get('unknown'):triangles[index]+=counts['unknown']
        check=checker.check(arm,body,time,tick,on_triangle=collect)
        segments,hands,_=checker.models[(time,tick)]
        lengths={n:v['length'] for n,v in checker.axes[arm]['axes'].items() if n in hands['segments']}
        intervals=at(probe,sampler,tick,arm,time,segments,helpers,axis_lengths=lengths)
        slot=probe.slots[arm];mesh=document['skins'][0]['attachments'][arm][slot['attachment']]
        influences=[];data=mesh['vertices'];cursor=0
        while cursor<len(data):
            count=data[cursor];cursor+=1;items=[]
            for _ in range(count):
                index,x,y,weight=data[cursor:cursor+4];cursor+=4
                if weight<=0:continue
                bone=document['bones'][index];name=bone['name'];length=lengths.get(name,bone.get('length',0))
                status=('helper_plane' if name in intervals['helper_planes'] else
                        'missing_source_segment' if name not in segments else
                        'invalid_axis_length' if length<=0 else
                        'outside_axis_cap' if not -.25*length<=x<=1.25*length else 'axis_supported')
                items.append(dict(bone=name,x=x,y=y,weight=weight,axis_length=length,status=status))
            influences.append(items)
        unknown=sorted({v for t in triangles for v in mesh['triangles'][3*t:3*t+3] if intervals['intervals'][v] is None})
        rows.append(dict(pair=record['pair'],time=time,counts=check['counts'],
            triangles=[dict(triangle=t,pixel_observations=n) for t,n in sorted(triangles.items())],
            unknown_vertices=[dict(vertex=v,influences=influences[v]) for v in unknown],
            influence_status_counts=dict(Counter(i['status'] for v in unknown for i in influences[v]))))
        print(f'{arm} at {time}: {len(unknown)} unknown vertices',flush=True)
    result=dict(profile='unknown-depth-weight-location-v1',job_id=job,artifact_sha256=artifact,
                input_evidence_sha256=sha256(evidence_bytes).hexdigest(),
                records=rows,authority='none',selected=False,
                scope='existing_valid_helper_instants_only_triangle_counts_may_overlap_not_error_rate')
    with urlopen('http://127.0.0.1:8918/api/motions/'+job,timeout=60) as response:
        if json.load(response)!=current:raise ValueError('candidate_changed')
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job');parser.add_argument('evidence',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.job,args.evidence,args.output)
