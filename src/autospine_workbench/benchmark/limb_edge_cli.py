"""Reversible local edge transfer; skeleton and animation are byte-identical."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from PIL import Image
from .artifacts import read_input, read_report, publish_report
from .mesh_storage import read_mesh_report
from .residual_location_cli import build as replay_locations
from .seam_candidate_hub import bundle_bytes
from .wing_spine_preview import encode
from .elbow_target_cli import archive
from ..asset.planning.wing_edge_ownership import decode, encode as png
from ..asset.planning.limb_edge_transfer import transfer
from ..resolved_project import canonical_sha256


def build(source, files, locations, ownership):
    if source['schema']!='autospine.wing-limb-preview/v1' or locations['source_preview_sha256']!=canonical_sha256(source):
        raise ValueError('limb_edge_source')
    if source['authority']!='none' or source['production_authorized'] is not False:
        raise ValueError('limb_edge_authority')
    if canonical_sha256(ownership)!=source['source_ownership_sha256']:
        raise ValueError('limb_edge_ownership')
    if set(files)!=set(source['files']) or any(sha256(files[n]).hexdigest()!=h for n,h in source['files'].items()):
        raise ValueError('limb_edge_files')
    doc=json.loads(files['skeleton.json']); outputs=dict(files); reports=[]
    for layer in ownership['layers']:
        name=layer['layer_id']; context='context-'+name; parts=[p['id'] for p in layer['partitions']]
        samples={tuple(t) for row in locations['rows'] if row['id']==name for p in row['points'] if p['mapping'] for t in p['mapping']['texel_neighborhood']}
        images={n:files['editor/images/'+n+'.png'] for n in parts}
        updated,residual,qa=transfer(images,files['editor/images/'+context+'.png'],
                                    {n:doc['skins'][0]['attachments'][n][n] for n in parts},samples)
        qa.update(layer_id=name,sample_texels=len(samples)); reports.append(qa)
        if not qa['changes']: continue
        page=decode(files['textures/'+name+'.png'])
        for part in layer['partitions']:
            tile=next(t for t in layer['tiles'] if t['owner_code']==part['tile_owner_code'])
            x,y,w,h=tile['rect']; image=decode(updated[part['id']])
            if image.size!=(w,h): raise ValueError('limb_edge_tile_size')
            page.paste(image,(x,y)); outputs['editor/images/'+part['id']+'.png']=updated[part['id']]
        tile=next(t for t in layer['tiles'] if t['owner_code']==layer['residual']['owner_code'])
        rest=decode(residual); page.paste(rest,tuple(tile['rect'][:2]))
        outputs['textures/'+name+'.png']=png(page)
        padded=Image.new('RGBA',(rest.width+4,rest.height+4)); padded.paste(rest,(2,2))
        outputs['textures/'+context+'.png']=png(padded); outputs['editor/images/'+context+'.png']=residual
        outputs['limb-residual/'+name+'.png']=residual
    total=sum(r['counts']['transferred'] for r in reports)
    report=deepcopy(source)
    report.update(schema='autospine.limb-edge-preview/v1',profile='sample-scoped-unique-limb-edge-2px-v1',
                  source_union_sha256=canonical_sha256(source),source_locations_sha256=canonical_sha256(locations),
                  edge_transfers=reports,transferred_pixels=total,skeleton_animation_unchanged=True,
                  candidate_status='needs_review' if total else 'reviewed_noop')
    outputs['edge-transfers.json']=encode(reports)
    outputs['README.txt']+=b'\nSample-scoped low-alpha transfer candidate. Unique 2px solid neighbor and existing mesh coverage required. No new weights or authority. Original skeleton/animation unchanged.\n'
    rows=''.join(f'<tr><td>{r["layer_id"]}</td><td>{r["sample_texels"]}</td><td>{r["counts"]["transferred"]}</td><td>{r["counts"]["no_neighbor"]}</td><td>{r["counts"]["ambiguous"]}</td><td>{r["counts"]["outside_mesh"]}</td></tr>' for r in reports)
    outputs['review.html']=f'''<!doctype html><meta charset="utf-8"><title>低透明度边缘归属候选</title><style>body{{font:18px/1.7 system-ui;margin:40px}}td,th{{padding:12px}}</style>
<h1>局部边缘归属候选</h1><p>共转移 {total} 个alpha 1–7像素。仅使用已定位采样邻域；没有改动骨骼、权重或动作。</p>
<table><tr><th>源层</th><th>采样texel</th><th>转移</th><th>无邻近区域</th><th>归属歧义</th><th>网格未覆盖</th></tr>{rows}</table>
<p><a href="preview.zip">下载候选包</a> · <a href="edge-transfers.json">逐像素转移记录</a></p><p>这是候选，仍需同帧Runtime对照，未批准为最终绑定结果。</p>'''.encode()
    outputs.pop('preview-manifest.json',None)
    report['files']={n:sha256(r).hexdigest() for n,r in outputs.items()};outputs['preview-manifest.json']=encode(report)
    return report,outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','locations','capture','manifest','output-dir'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'));args=parser.parse_args()
    source,locations,capture=map(read_input,[args.source,args.locations,args.capture]);dataset=read_input(args.manifest)['dataset_id']
    if read_report(args.state_root,dataset,'wing-limb-previews-v1',canonical_sha256(source))!=source:raise ValueError('limb_edge_source_address')
    expected,_=replay_locations(capture,bundle_bytes(args.capture.parent,capture['files']))
    if expected!=locations:raise ValueError('limb_edge_locations_replay')
    ownership=read_mesh_report(args.state_root,dataset,source['source_ownership_sha256'])
    report,files=build(source,bundle_bytes(args.source.parent,source['files']),locations,ownership);files['preview.zip']=archive(files)
    for name,raw in files.items():
        path=args.output_dir/name
        if path.exists() and path.read_bytes()!=raw:raise ValueError('limb_edge_existing_changed')
    digest=publish_report(args.state_root,dataset,'limb-edge-previews-v1',report)
    for name,raw in files.items():
        path=args.output_dir/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    print(digest);print([(r['layer_id'],r['counts']) for r in report['edge_transfers']])


if __name__=='__main__':main()
