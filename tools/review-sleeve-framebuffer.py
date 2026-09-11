"""Check byte-bound capture receipts and produce an ordinary visual review index."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from html import escape
from autospine_workbench.targets.spine43.sleeve_framebuffer import summarize
from autospine_workbench.automation.sleeve_motion_inventory import explicit_frame_count
from autospine_workbench.targets.spine43.sleeve_overlap_framebuffer import summaries as overlap_summaries,render as overlap_render


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--contacts',type=Path,required=True)
    p.add_argument('--overlap',type=Path)
    args=p.parse_args();rows=[];frames=samples=failed=0
    for path in sorted(args.input.glob('*/*/*.json')):
        raw=path.read_bytes();doc=json.loads(raw)
        if hashlib.sha256(raw).hexdigest()!=path.stem:raise ValueError('capture_digest')
        if (doc['project_id']!=path.parent.parent.name or not re.fullmatch(r'[a-zA-Z0-9_-]+',doc['project_id'])
                or not re.fullmatch(r'[a-f0-9]{64}',doc['contact_sha256'])):raise ValueError('capture_path')
        contact_path=args.contacts/doc['project_id']/(doc['contact_sha256']+'.json')
        contact_raw=contact_path.read_bytes()
        if hashlib.sha256(contact_raw).hexdigest()!=doc['contact_sha256']:raise ValueError('contact_digest')
        contact=json.loads(contact_raw)
        if contact['source_sha256']!=doc['source_sha256']:raise ValueError('contact_source')
        matches=[r for r in contact['records'] if (r['layer_id'],r['component_id'])==(doc['layer_id'],doc['component_id'])]
        if len(matches)!=1 or matches[0]['asset_sha256']!=doc['asset_sha256']:raise ValueError('capture_assets')
        summary=summarize(doc,matches[0]);frames+=summary['frames'];samples+=summary['tested_samples'];failed+=summary['failed_samples']
        extra=[];overlap_html=''
        if doc.get('overlap'):
            if args.overlap is None:raise ValueError('overlap_source_required')
            sha=doc['overlap']['source_sha256']
            if not re.fullmatch(r'[a-f0-9]{64}',sha):raise ValueError('overlap_digest')
            raw=(args.overlap/doc['project_id']/(sha+'.json')).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('overlap_digest')
            source=json.loads(raw)
            if source['source_report_sha256']!=doc['source_sha256']:raise ValueError('overlap_source')
            match=[r for r in source['records'] if (r['layer_id'],r['component_id'])==(doc['layer_id'],doc['component_id'])]
            if len(match)!=1 or match[0]['asset_sha256']!=doc['asset_sha256']:raise ValueError('overlap_assets')
            results=overlap_summaries(doc['overlap'],match[0])
            extra=[i for c in doc['overlap']['captures'] for i in c['images']]
            extra += [c['context'] for c in doc['overlap']['captures'] if c.get('context')]
            overlap_html=overlap_render(doc['overlap'],results,lambda f:(path.parent/f).relative_to(args.input).as_posix(),doc['info'])
        for c in doc['captures']+extra:
            image=path.parent/c['file']
            if image.resolve().parent!=path.parent.resolve() or hashlib.sha256(image.read_bytes()).hexdigest()!=c['sha256']:
                raise ValueError('capture_image')
        label=escape(doc['project_id']+' / '+doc['layer_id'])
        href=escape(path.relative_to(args.input).as_posix(),quote=True)
        examples=[]
        for c in doc['captures']:
            example='combined_same' if doc.get('motion_profile') in ('ordinary-forearm30-hand30-sine129-v1','ordinary-deform-local129-quarter513-v1') else 'combined_pm'
            rate=(explicit_frame_count(doc)-1)//2 if doc['schema'].endswith('/v2') else 128
            if c['animation']==example and c['index'] in (0,rate//2,rate*3//2):
                src=escape((path.parent/c['file']).relative_to(args.input).as_posix(),quote=True)
                examples.append(f'<figure><img src="{src}"><figcaption>{c["animation"]} · {c["index"]}/{rate} 秒</figcaption></figure>')
        rows.append(f'<section><h2>{label}</h2><p>{summary["frames"]} 帧；{summary["tested_samples"]} 探针；空白失败 {summary["failed_samples"]}；最低 alpha {summary["min_alpha"]}。</p><a href="{href}">精确报告</a><div>{"".join(examples)}</div>{overlap_html}</section>')
    if not rows:raise ValueError('capture_missing')
    html=f'''<!doctype html><meta charset="utf-8"><title>四袖官方 Runtime 捕获</title>
<style>body{{background:#16212c;color:#eef;font:17px system-ui;margin:32px}}a{{color:#6df}}figure{{display:inline-block;margin:8px;width:28%}}img{{width:100%;background:repeating-conic-gradient(#384552 0% 25%,#293540 0% 50%) 0/16px 16px}}section{{border-top:1px solid #567;margin-top:28px}}p{{line-height:1.7}}</style>
<h1>官方 WebGL 袖装捕获</h1><p>Spine 4.3.26 导出 · 官方 spine-webgl 4.3.13 · ANGLE SwiftShader 软件图形后端。</p>
<p>共 {frames} 帧、{samples} 个袖口探针、空白失败 {failed}。仅证明指定探针在当前渲染配置下的覆盖；自重叠、完整角色与独立样本仍待复核。没有正式采用或生产授权。</p>{''.join(rows)}'''
    (args.input/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(regions=len(rows),frames=frames,tested_samples=samples,failed_samples=failed)))


if __name__=='__main__':main()
