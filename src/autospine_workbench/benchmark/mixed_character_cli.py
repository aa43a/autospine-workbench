"""Source-replayed mixed Spine candidate with explicit missing layers."""
import argparse
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from ..resolved_project import canonical_sha256
from ..targets.spine43.mixed_character import compose
from ..targets.spine43.continuous_pose import inspect,world
from ..asset.joints.partition_pixels import png
from .artifacts import read_input
from .layer_binding_cli import read_layer_binding_draft,read_layer_bindings
from .region_binding_cli import sources
from .ownership_atlas_cli import read_atlas
from .seam_candidate_hub import bundle_bytes
from .elbow_target_cli import archive


def build(state,manifest,workspace,atlas_path,candidate_path,draft_path):
    draft=read_layer_binding_draft(state,manifest,canonical_sha256(read_input(draft_path)),workspace=workspace)
    bindings=read_layer_bindings(state,manifest,draft['source_bindings_sha256'],workspace=workspace)
    source,_,skeleton,_,images=sources(state,manifest,bindings['source_skeleton_sha256'],workspace)
    atlas=read_atlas(state,manifest,canonical_sha256(read_input(atlas_path)),workspace=workspace)
    candidate=json.loads(candidate_path.read_bytes())
    if candidate['schema']!='autospine.seam-stable-fallback/v1':raise ValueError('mixed_candidate_profile')
    files=bundle_bytes(candidate_path.parent,candidate['files']);previous=json.loads(files['preview-manifest.json'])
    doc,rigid,excluded=compose(json.loads(files['skeleton.json']),source,skeleton,atlas,bindings,draft)
    originals={r['layer_id']:r for r in source['layers']}; regions=deepcopy(previous['regions'])
    atlas_text=files['skeleton.atlas'].decode();setup=world(doc,0)
    for name in rigid:
        raw=images[name];x,y,r,b=originals[name]['bbox'];w,h=r-x,b-y
        with Image.open(BytesIO(raw)) as image:
            page=Image.new('RGBA',(w+4,h+4));page.paste(image.convert('RGBA'),(2,2))
            page_raw=png('RGBA',page.size,page.tobytes())
        texture='textures/rigid-'+name+'.png';files[texture]=page_raw;files['editor/images/'+name+'.png']=raw
        atlas_text+=f'\n{texture}\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{name}\nbounds: 2,2,{w},{h}\n\n'
        expected=[[x,y],[r,y],[r,b],[x,b]]
        error=max(abs(a-b) for got,want in zip(setup[name],expected) for a,b in zip(got,[want[0],-want[1]]))
        if error>1e-6:raise ValueError('mixed_rigid_setup_reconstruction')
        regions.append(dict(id=name,expected_page_uvs=[[2/(w+4),2/(h+4)],[(w+2)/(w+4),2/(h+4)],[(w+2)/(w+4),(h+2)/(h+4)],[2/(w+4),(h+2)/(h+4)]],setup_vertices_xy=expected,source_mesh_status='rigid_binding_selected',review_status='selected'))
    encode=lambda d:json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    files['skeleton.atlas']=atlas_text.encode();files['skeleton.json']=encode(doc)
    editor=deepcopy(doc);editor['skeleton']['images']='./images/';files['editor/skeleton.json']=encode(editor)
    files.pop('preview-manifest.json');geometry=inspect(doc)
    scope=dict(profile='selected-rigid-quads-with-partition-candidates-v1',authority='none',production_authorized=False,status='needs_review',
               full_character_animation='blocked',draw_order='source_order_unreviewed',source_candidate_sha256=canonical_sha256(candidate),
               source_draft_sha256=canonical_sha256(draft),source_atlas_sha256=canonical_sha256(atlas),rigid_layers=rigid,
               excluded_layers=excluded,residual_visible_pixels=sum(l['residual']['visible_pixels'] for l in atlas['layers']))
    preview=dict(scope,schema='autospine.mixed-character-preview/v1',animation=previous['animation'],regions=regions,bake_qa=geometry,
                 shape_qa=previous['shape_qa'],files={n:hashlib.sha256(r).hexdigest() for n,r in files.items()})
    files['preview-manifest.json']=encode(preview)
    report=dict(scope,geometry=geometry,files={n:hashlib.sha256(r).hexdigest() for n,r in files.items()})
    from .mixed_character_view import render
    # Review page is outside the hashed runtime payload and its deterministic ZIP.
    report_page=render(report,{n:r['name'] for n,r in originals.items()})
    files['review.html']=report_page.encode('utf-8')
    return report,files


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('state-root','manifest','workspace','atlas','candidate','draft','output-dir'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();report,files=build(a.state_root,read_input(a.manifest),a.workspace,a.atlas,a.candidate,a.draft)
    a.output_dir.mkdir(parents=True,exist_ok=True);target=a.output_dir/(canonical_sha256(report)+'.json')
    if target.exists() and json.loads(target.read_bytes())!=report:raise ValueError('mixed_existing_corrupt')
    for name,raw in files.items():
        path=a.output_dir/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');(a.output_dir/'preview.zip').write_bytes(archive({n:r for n,r in files.items() if n!='review.html'}))
    print(json.dumps(dict(artifact=target.stem,rigid=report['rigid_layers'],excluded=len(report['excluded_layers']),regions=len(report['geometry']['regions']))))


def read_mixed(saved,*sources):
    expected,_=build(*sources)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('mixed_replay')
    return saved


if __name__=='__main__':main()
