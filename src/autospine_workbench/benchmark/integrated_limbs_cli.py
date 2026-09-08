"""Replay selected elbow meshes and integrate them with the mixed candidate package."""
import argparse
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from ..resolved_project import canonical_sha256
from ..targets.spine43.merge_limb_tracks import merge
from ..targets.spine43.continuous_pose import world,inspect
from ..asset.joints.partition_pixels import png
from .artifacts import read_input
from .character_preview_cli import build as donor_build
from .seam_candidate_hub import bundle_bytes
from .elbow_target_cli import archive
from .mixed_character_view import render
from .mesh_storage import read_mesh_report


def build(state,manifest,workspace,base_path,donor_path):
    base=json.loads(base_path.read_bytes());donor=read_input(donor_path)
    if base['profile']!='selected-rigid-quads-with-partition-candidates-v1':raise ValueError('integrated_base_profile')
    _,scope,scene=donor_build(state,manifest,donor['source_bake_sha256'],workspace)
    if canonical_sha256(scope)!=canonical_sha256(donor):raise ValueError('integrated_donor_replay')
    source,skeleton,mesh,bake,donor_doc,_,images,_=scene
    if base['source_draft_sha256']!=donor['source_draft_sha256']:raise ValueError('integrated_selection_identity')
    files=bundle_bytes(base_path.parent,base['files']);preview=json.loads(files['preview-manifest.json']);old=json.loads(files['skeleton.json'])
    names=[r['layer_id'] for r in base['excluded_layers'] if r['reason_code']=='selected_mesh_candidate_not_integrated']
    doc=merge(old,donor_doc,names)
    order={r['layer_id']:i for i,r in enumerate(source['layers'])};source_names={r['layer_id']:r['name'] for r in source['layers']}
    # Preserve exact existing partition grouping; insert whole-source arms by source order.
    ownership=read_mesh_report(state,manifest['dataset_id'],base['source_atlas_sha256'])
    owner={p['id']:layer['layer_id'] for layer in ownership['layers'] for p in layer['partitions']}
    owner.update({n:n for n in base['rigid_layers']})
    if set(owner)!={s['name'] for s in old['slots']} or not set(owner.values()).issubset(order):raise ValueError('integrated_partition_owner')
    owner.update({n:n for n in names});doc['slots'].sort(key=lambda s:order[owner[s['name']]])
    for i in range(121):
        before,after=world(old,i/60),world(doc,i/60)
        if any(before[n]!=after[n] for n in before):raise ValueError('integrated_existing_motion_changed')
    originals={r['layer_id']:r for r in mesh['layers']};atlas=files['skeleton.atlas'].decode();regions=deepcopy(preview['regions'])
    for name in names:
        a=doc['skins'][0]['attachments'][name][name];w,h=a['width'],a['height'];raw=images[name]
        with Image.open(BytesIO(raw)) as image:
            page=Image.new('RGBA',(w+4,h+4));page.paste(image.convert('RGBA'),(2,2));page_raw=png('RGBA',page.size,page.tobytes())
        texture='textures/arm-'+name+'.png';files[texture]=page_raw;files['editor/images/'+name+'.png']=raw
        atlas+=f'\n{texture}\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{name}\nbounds: 2,2,{w},{h}\n\n'
        uvs=list(zip(a['uvs'][::2],a['uvs'][1::2]));regions.append(dict(id=name,expected_page_uvs=[[(2+u*w)/(w+4),(2+v*h)/(h+4)] for u,v in uvs],setup_vertices_xy=originals[name]['vertices_xy'],source_mesh_status='selected_elbow_bake',review_status='selected'))
    encode=lambda d:json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    files['skeleton.json']=encode(doc);editor=deepcopy(doc);editor['skeleton']['images']='./images/';files['editor/skeleton.json']=encode(editor);files['skeleton.atlas']=atlas.encode();files.pop('preview-manifest.json')
    geometry=inspect(doc);excluded=[r for r in base['excluded_layers'] if r['layer_id'] not in names]
    report={k:deepcopy(base[k]) for k in ('authority','production_authorized','status','full_character_animation','draw_order','rigid_layers','residual_visible_pixels')}
    report.update(profile='selected-elbow-and-leg-candidate-union-v1',source_base_sha256=canonical_sha256(base),source_donor_sha256=canonical_sha256(donor),integrated_arms=names,excluded_layers=excluded,geometry=geometry)
    preview.update({k:v for k,v in report.items() if k!='geometry'})
    preview.update(regions=regions,bake_qa=geometry,excluded_layers=excluded,integrated_arms=names,schema='autospine.integrated-limbs-preview/v1',files={n:hashlib.sha256(r).hexdigest() for n,r in files.items()})
    files['preview-manifest.json']=encode(preview);report['files']={n:hashlib.sha256(r).hexdigest() for n,r in files.items()}
    page=render(report,source_names)
    return report,files,page


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('state-root','manifest','workspace','base','donor','output-dir'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();report,files,page=build(a.state_root,read_input(a.manifest),a.workspace,a.base,a.donor)
    a.output_dir.mkdir(parents=True,exist_ok=True);target=a.output_dir/(canonical_sha256(report)+'.json')
    if target.exists() and json.loads(target.read_bytes())!=report:raise ValueError('integrated_existing_corrupt')
    for name,raw in files.items():
        path=a.output_dir/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');(a.output_dir/'preview.zip').write_bytes(archive(files));(a.output_dir/'review.html').write_text(page,encoding='utf-8')
    print(json.dumps(dict(artifact=target.stem,arms=report['integrated_arms'],excluded=len(report['excluded_layers']),passed=all(r['passed'] for r in report['geometry']['regions'].values()))))


def read_integrated(saved,*sources):
    expected,_,_=build(*sources)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('integrated_replay')
    return saved


if __name__=='__main__':main()
