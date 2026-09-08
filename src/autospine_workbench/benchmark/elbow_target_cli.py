"""Export a reproducible selected-mesh ZIP without assuming unreviewed bindings."""
import hashlib
import io
import json
from pathlib import Path
import os
import tempfile
import zipfile
from ..automation.storage_io import directory
from ..safe_input_files import read_real_file,strict_json_object
from ..spine42_v3_bundle_files import existing_exact_child
from ..resolved_project import canonical_sha256
from ..targets.spine43.elbow_preview import build_preview
from .artifacts import read_input,read_report
from .mesh_storage import read_mesh_report
from .elbow_bake_cli import sources


def register_parser(sub):
    cmd=sub.add_parser('export-elbow-spine43',help='Export selected corrective meshes for Spine 4.3.26 inspection')
    for name in ('manifest','workspace','bake','zip'):cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)


def archive(files):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive_file:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive_file.writestr(info,data)
    return buffer.getvalue()


def export(path,data):
    root=directory(path.parent,create=True)
    existing=existing_exact_child(root,path.name)
    if existing is not None:
        if existing.lstat().st_nlink!=1 or read_real_file(existing,32<<20,'preview zip')!=data:raise ValueError('elbow_preview_output_exists')
        return
    fd,name=tempfile.mkstemp(dir=root,prefix='.elbow-')
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.link(name,path)
    finally:Path(name).unlink(missing_ok=True)


def build_archive(mesh,skeleton,bake,candidate,images):
    doc,scope=build_preview(mesh,skeleton,bake,candidate)
    files={'skeleton.json':json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()}
    originals={r['layer_id']:r for r in candidate['layers']};pages=[]
    for name in scope['included_layers']:
        image=images[name]
        if hashlib.sha256(image).hexdigest()!=originals[name]['image_sha256']:raise ValueError('elbow_preview_image_mismatch')
        files[f'images/{name}.png']=image
        x,y,r,b=originals[name]['bbox'];w,h=r-x,b-y
        pages.append(f'images/{name}.png\nsize: {w},{h}\nfilter: Linear,Linear\npma: false\n{name}\nbounds: 0,0,{w},{h}\n')
    files['skeleton.atlas']='\n'.join(pages).encode()
    scope['files']={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    files['preview-manifest.json']=json.dumps(scope,sort_keys=True,indent=2).encode()
    files['README.txt']=b'Diagnostic subset only. Import skeleton.json with images/ beside it. Select elbow-diagnostic. Not a full character or approved Runtime export. See preview-manifest.json.\n'
    data=archive(files)
    if len(data)>32<<20:raise ValueError('elbow_preview_too_large')
    scope['zip_sha256']=hashlib.sha256(data).hexdigest()
    return data,scope


def read_target_preview(state,manifest,digest,*,workspace):
    report=read_report(state,manifest['dataset_id'],'elbow-target-previews',digest)
    bake=read_mesh_report(state,manifest['dataset_id'],report['source_bake_sha256'])
    mesh,skeleton,candidate,images=sources(state,manifest,bake['source_mesh_sha256'],workspace)
    _,expected=build_archive(mesh,skeleton,bake,candidate,images)
    if canonical_sha256(expected)!=canonical_sha256(report):raise ValueError('elbow_target_preview_mismatch')
    return report


def execute(args):
    manifest=read_input(args.manifest)
    digest=canonical_sha256(strict_json_object(read_real_file(args.bake,16<<20,'bake'),'bake'))
    bake=read_mesh_report(args.state_root,manifest['dataset_id'],digest)
    mesh,skeleton,candidate,images=sources(args.state_root,manifest,bake['source_mesh_sha256'],args.workspace)
    data,scope=build_archive(mesh,skeleton,bake,candidate,images)
    export(args.zip,data)
    return scope,'elbow-target-previews',manifest['dataset_id'],0
