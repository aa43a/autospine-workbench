"""Verify the explicit original-texture regression; never accept animation quality."""
from argparse import ArgumentParser
from hashlib import sha256
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.numeric_reference import read


def verify(state, candidate, output):
    store=AnimatedStore(state);files=store.read(candidate)
    provenance=json.loads(files['motion-repair-provenance.json'])
    parent=store.read(provenance['parent_artifact_sha256'])
    doc=json.loads(files['skeleton.json']);original=json.loads(parent['skeleton.json'])
    report=json.loads(files['view-pose-report.json']);variant=report['variant']
    slot,name=variant['slot'],variant['animation'];new_name=variant['variant_attachment']
    mesh=doc['skins'][0]['attachments'][slot][new_name]
    old=original['skins'][0]['attachments'][slot][slot]
    assert doc['bones']==original['bones'] and doc['slots']==original['slots']
    assert mesh['uvs']==old['uvs'] and mesh['vertices']==old['vertices']
    texture=files['images/'+mesh['path']+'.png']
    source_texture=parent['images/'+old.get('path',slot)+'.png']
    assert texture==source_texture and sha256(texture).hexdigest()==report['texture_sha256']
    frames=read(files)['animations'][name];before=read(parent)['animations'][name]
    lookup={r['time']:r for r in frames};maximum=0.
    for frame in before:
        after=lookup[frame['time']]
        assert set(after['vertices'])==set(frame['vertices'])
        for key,points in frame['vertices'].items():
            assert len(points)==len(after['vertices'][key])
            maximum=max(maximum,max(math.dist(a,b) for a,b in zip(points,after['vertices'][key])))
    assert maximum<=1e-6
    begin,end=variant['runtime_interval'];active=0
    for row in frames:
        expected=new_name if begin<=row['time']<end else slot
        assert row['attachments'][slot]==expected
        active+=expected==new_name
    assert 0<active<len(frames)
    quality=json.loads(files['deformation.json']);review=json.loads(files['motion-review.json'])
    assert not review['selected'] and not review['production_authorized']
    assert not quality['passed'],'This regression is expected to retain parent geometry failures'
    result=dict(candidate_sha256=candidate,parent_sha256=provenance['parent_artifact_sha256'],
        original_frames=len(before),candidate_frames=len(frames),variant_frames=active,
        max_original_frame_error_px=maximum,original_texture_preserved=True,
        geometry_passed=quality['passed'],selected=False,scope='original_texture_transport_not_visual_repair')
    output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':
    parser=ArgumentParser();parser.add_argument('--state',type=Path,default=Path('workspace'))
    parser.add_argument('--candidate',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();verify(args.state,args.candidate,args.output)
