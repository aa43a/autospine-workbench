"""Locate stable and unresolved source triangles across garment hypotheses."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.depth_trace_feasibility import inspect


def run(diagnostic,partition,output):
    if output.exists():raise ValueError('output_exists')
    raw=diagnostic.read_bytes();report=json.loads(raw);proof=json.loads((partition/'report.json').read_bytes())
    skeleton=(partition/'skeleton.json').read_bytes();doc=json.loads(skeleton)
    if (report['source_artifact_sha256']!=proof['source_artifact_sha256']
            or report['skeleton_sha256']!=proof['skeleton_sha256']
            or report['skeleton_sha256']!=sha256(skeleton).hexdigest()
            or report.get('spatial_sampling')!='barycentric_pixel_intervals'
            or report.get('triangle_traces') is not True):raise ValueError('trace_feasibility_identity')
    groups={r['slot']:r for r in proof['partition']['regions']};rows=[];counts=Counter();seen=set()
    for row in report['rows']:
        region=row['region'];time=row['time'];key=(region,row['body'],time)
        if key in seen:raise ValueError('trace_feasibility_duplicate_sample')
        seen.add(key)
        if any(h['pair']!=[region,row['body']] or h['time']!=time for h in row['hypotheses']):
            raise ValueError('trace_feasibility_sample_identity')
        if [h['aspect_max'] for h in row['hypotheses']]!=report['tested_aspect_max']:
            raise ValueError('trace_feasibility_hypothesis_inventory')
        mesh=doc['skins'][0]['attachments'][region][region];parent=groups[region]
        result=inspect(row['hypotheses'],len(mesh['triangles'])//3)
        for tri in result['triangles']:tri['source_triangle']=parent['triangles'][tri['triangle']]
        counts.update(result['counts'])
        rows.append(dict(result,region=region,source_slot=parent['source_slot'],body=row['body'],
                         time=time,source_tick=row['source_tick']))
    result=dict(profile='sampled-existing-triangle-depth-feasibility-v1',
        source_artifact_sha256=report['source_artifact_sha256'],skeleton_sha256=sha256(skeleton).hexdigest(),
        diagnostic_sha256=sha256(raw).hexdigest(),rows=rows,triangle_sample_counts=dict(counts),
        unresolved_region_samples=sum(not r['existing_triangle_split_fully_decidable'] for r in rows),
        subtriangle_or_model_change_samples=sum(r['requires_subtriangle_or_model_change'] for r in rows),
        authority='none',selected=False,scope='sampled_hypothesis_feasibility_not_surface_or_visual_acceptance')
    with output.open('xb') as stream:stream.write(canonical_bytes(result))
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('diagnostic','partition','output'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.diagnostic,a.partition,a.output)
