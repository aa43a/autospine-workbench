"""Compare matching official Runtime captures after texture-only changes."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes


def compare(before,after,state_root):
    from PIL import Image,ImageChops
    old=json.loads((before/'report.json').read_bytes());new=json.loads((after/'report.json').read_bytes())
    for key in ('runtime_sha256','harness_sha256','browser_sha256','runtime_version','profile','info'):
        if old[key]!=new[key]:raise ValueError('transfer_capture_context_mismatch:'+key)
    store=AnimatedStore(state_root);a=store.read(old['bundle_sha256']);b=store.read(new['bundle_sha256'])
    for name in a:
        if name=='skeleton.json' or name=='skeleton.atlas' or name.startswith('numeric-reference'):
            if a[name]!=b.get(name):raise ValueError('transfer_capture_geometry_changed')
    previous={r['file']:r for r in old['screenshots']};rows=[]
    def frame(root,row):
        name=row['file'];path=root/name
        if not path.resolve().is_relative_to(root.resolve()):raise ValueError('transfer_capture_path')
        raw=path.read_bytes()
        if sha256(raw).hexdigest()!=row['sha256']:raise ValueError('transfer_capture_digest')
        return Image.open(BytesIO(raw)).convert('RGBA')
    for row in new['screenshots']:
        prior=previous.get(row['file'])
        if not prior or any(prior[k]!=row[k] for k in ('animation','index')):
            raise ValueError('transfer_capture_pair_missing')
        left=frame(before,prior);right=frame(after,row)
        if left.size!=right.size:raise ValueError('transfer_capture_size')
        delta=ImageChops.difference(left,right);raw=delta.tobytes()
        composite={}
        for label,shade in [('black',0),('white',255)]:
            background=Image.new('RGBA',left.size,(shade,shade,shade,255))
            d=ImageChops.difference(Image.alpha_composite(background,left),Image.alpha_composite(background,right))
            composite['max_'+label+'_background_delta']=max(high for _,high in d.getextrema())
        rows.append(dict(animation=row['animation'],index=row['index'],
            changed_pixels=sum(any(raw[i:i+4]) for i in range(0,len(raw),4)),
            max_channel_delta=max(raw),max_alpha_delta=max(raw[3::4]),**composite))
    return dict(schema='autospine.texture-transfer-runtime-comparison/v1',authority='none',selected=False,
        before_bundle=old['bundle_sha256'],after_bundle=new['bundle_sha256'],
        before_report_sha256=sha256((before/'report.json').read_bytes()).hexdigest(),
        after_report_sha256=sha256((after/'report.json').read_bytes()).hexdigest(),
        runtime_passed=new['passed'],compared_frames=len(rows),rows=rows,
        scope='matching_captured_frames_not_visual_acceptance_or_all_pixel_times')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True)
    p.add_argument('--state-root',type=Path,default=Path('workspace'));p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=compare(args.before,args.after,args.state_root)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(canonical_bytes(r))
    print(json.dumps(dict(frames=r['compared_frames'],max_channel_delta=max(v['max_channel_delta'] for v in r['rows']),
                         max_changed_pixels=max(v['changed_pixels'] for v in r['rows']),runtime_passed=r['runtime_passed'])))
