"""Replay ordinary deform closure and emit diagnostic Spine candidates with exact textures."""
import argparse
from copy import deepcopy
import hashlib
from html import escape
import json
from pathlib import Path
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.benchmark.mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from autospine_workbench.benchmark.elbow_target_cli import export,archive
from autospine_workbench.asset.planning.component_partitions import build as partition
from autospine_workbench.asset.planning.component_mesh import isolated_png
from autospine_workbench.targets.spine43.ordinary_deform import build
from autospine_workbench.targets.spine43.continuous_pose import world
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.manifest_artifacts import require_safe_token


def encoded(doc):
    return json.dumps(doc,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project');parser.add_argument('--interpolation',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    parser.add_argument('--workspace',type=Path,default=Path('..'))
    args=parser.parse_args();require_safe_token(args.project,'project')
    read=lambda sha:read_mesh_report(args.state_root,'project-component-partitions',sha)
    interpolation=read(args.interpolation);deform=read(interpolation['deform_sha256'])
    if deform['project_id']!=args.project:raise ValueError('ordinary_target_project_mismatch')
    repair,source,draft=[read(deform[k]) for k in ('repair_sha256','source_sha256','draft_sha256')]
    store=ProjectStore(args.workspace.resolve(),args.state_root.resolve())
    with load_inputs(store,args.project) as inputs:
        report,documents=build(interpolation,deform=deform,repair=repair,source=source,draft=draft,skeleton=inputs.skeleton)
        layers={r['layer_id']:r for r in inputs.candidate['layers']};payloads={};links=[]
        for row in report['records']:
            label=row['layer_id']+'-'+row['component_id'];require_safe_token(label,'region')
            if row['status']!='target_sampled_passed':
                links.append(f'<li>{escape(label)}：阻塞 — {escape(", ".join(row["reason_codes"]))}</li>');continue
            doc=documents[row['target_sha256']];layer=layers[row['layer_id']];raw=inputs.images[row['layer_id']]
            parts=partition(layer,raw)
            region=next(r for r in parts['components']+[parts['residual']] if r['id']==row['component_id'])
            image=isolated_png(raw,region)
            if hashlib.sha256(image).hexdigest()!=row['isolated_image_sha256']:
                raise ValueError('ordinary_target_texture_identity')
            width=layer['bbox'][2]-layer['bbox'][0];height=layer['bbox'][3]-layer['bbox'][1]
            atlas=(f'images/{label}.png\nsize: {width},{height}\nfilter: Linear,Linear\npma: false\n'
                   f'repeat: none\n{label}\nbounds: 0,0,{width},{height}\n')
            files={'skeleton.json':encoded(doc),'skeleton.atlas':atlas.encode(),f'images/{label}.png':image}
            reference={}
            for name,animation in doc['animations'].items():
                probe=deepcopy(doc);probe['animations']={name:animation}
                reference[name]=[dict(time=i/256,points=world(probe,i/256)[label]) for i in range(513)]
            payloads[label]=(files,encoded(dict(skeleton_sha256=hashlib.sha256(files['skeleton.json']).hexdigest(),animations=reference)))
            links.append(f'<li>{escape(label)}：目标采样通过，待视觉与Runtime验证 — <a href="{escape(label)}/candidate.zip">候选ZIP</a></li>')
        inputs.assert_current()
        sha=publish_mesh_report(args.state_root,'project-component-partitions',report)
        if read(sha)!=report:raise ValueError('ordinary_target_readback_mismatch')
        args.output.mkdir(parents=True,exist_ok=True)
        export_mesh(args.output/(sha+'.json'),report)
        for digest,doc in documents.items():
            export(args.output/'diagnostics'/(digest+'.json'),encoded(doc))
        for label,(files,reference) in payloads.items():
            for name,raw in files.items():export(args.output/label/name,raw)
            export(args.output/label/'candidate.zip',archive(files))
            export(args.output/label/'numeric-reference.json',reference)
        page=('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>普通袖Spine deform检查</title>'
              '<style>body{background:#142331;color:#e4f0ff;font:16px system-ui;padding:24px}a{color:#70d9ff}li{margin:18px 0}</style>'
              '<h1>普通袖Spine 4.3.26 deform候选</h1><p>每轨513个时刻；UV与隔离纹理绑定原来源。'
              '关键帧容差1e-7px，帧间保真容差为中位边长1%，属于固定工程检查标准，不是视觉验收。</p>'
              '<p>尚未执行本候选的官方Runtime、透明接缝或视觉验收；没有生产采用或发布权。</p>'
              f'<ul>{"".join(links)}</ul><a href="{sha}.json">完整目标检查报告</a></html>')
        export(args.output/'index.html',page.encode('utf-8'))
        print(sha,flush=True)


if __name__=='__main__':main()
