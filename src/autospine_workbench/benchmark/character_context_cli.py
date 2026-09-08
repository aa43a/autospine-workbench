"""Exact source and candidate inventory before full-character animation integration."""
import argparse
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from .artifacts import read_input
from .ownership_atlas_cli import read_atlas
from .region_binding_cli import sources
from .seam_candidate_hub import bundle_bytes
from .character_context_view import cards,render


def build(state,manifest,workspace,atlas_path,candidate_path):
    saved=read_input(atlas_path)
    atlas=read_atlas(state,manifest,canonical_sha256(saved),workspace=workspace)
    source,_,skeleton,_,images=sources(state,manifest,atlas['source_skeleton_sha256'],workspace)
    candidate=json.loads(candidate_path.read_bytes())
    if candidate['schema']!='autospine.seam-stable-fallback/v1':raise ValueError('context_candidate_profile')
    files=bundle_bytes(candidate_path.parent,candidate['files']);doc=json.loads(files['skeleton.json'])
    expected=[]
    for bone in skeleton['bones']:
        local=bone['setup_local'];row=dict(name=bone['id'],x=local['x'],y=-local['y'],rotation=-local['rotation_degrees'],length=bone['length'])
        if bone['parent_id'] is not None:row['parent']=bone['parent_id']
        expected.append(row)
    if doc['bones']!=expected:raise ValueError('context_skeleton_identity')
    partitions=[p['id'] for layer in atlas['layers'] for p in layer['partitions']]
    region_images={name:files['editor/images/'+name+'.png'] for name in partitions}
    scene=cards(source,atlas,doc,images,region_images)
    represented={layer['layer_id'] for layer in atlas['layers']}
    rows=[dict(layer_id=r['layer_id'],name=r['name'],status='animated_partition_subset' if r['layer_id'] in represented else 'fixed_source_context_only') for r in source['layers']]
    report=dict(profile='source-order-static-context-with-candidate-partitions-v1',authority='none',production_authorized=False,
                status='needs_review',full_character_animation='blocked',draw_order='source_order_unreviewed',renderer='diagnostic_webgl_mesh_canvas2d_composite',
                source_candidate_sha256=canonical_sha256(source),source_atlas_sha256=canonical_sha256(atlas),
                source_animation_sha256=canonical_sha256(candidate),layers=rows,animated_partition_count=len(partitions),
                fixed_source_layer_count=len(rows)-len(represented),residual_visible_pixels=sum(l['residual']['visible_pixels'] for l in atlas['layers']))
    return report,render(source,scene,report)


def read_context(saved,*sources):
    expected,_=build(*sources)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('context_replay')
    return saved


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('state-root','manifest','workspace','atlas','candidate','output-dir'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();report,page=build(a.state_root,read_input(a.manifest),a.workspace,a.atlas,a.candidate)
    a.output_dir.mkdir(parents=True,exist_ok=True);target=a.output_dir/(canonical_sha256(report)+'.json')
    if target.exists() and json.loads(target.read_bytes())!=report:raise ValueError('context_existing_corrupt')
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');(a.output_dir/'index.html').write_text(page,encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='layers'}))


if __name__=='__main__':main()
