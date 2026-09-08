"""Confirmed-layer scene, shoulder contact candidates, and independent target ZIP."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file,strict_json_object
from ..targets.spine43.character_preview import build_character
from ..asset.joints.character_contacts import contacts
from .artifacts import read_input,read_report
from .mesh_candidate_cli import read_mesh_candidate,inputs
from .mesh_storage import read_mesh_report
from .elbow_target_cli import archive_document,export
from .mapping_cli import export_html


def register_parser(sub):
    cmd=sub.add_parser('compose-character-preview',help='Compose confirmed rigid and corrective layers with contact candidates')
    for name in ('manifest','workspace','bake','zip','html'):cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)


def build(state,manifest,digest,workspace):
    bake=read_mesh_report(state,manifest['dataset_id'],digest)
    mesh=read_mesh_candidate(state,manifest,bake['source_mesh_sha256'],workspace=workspace)
    candidate,_,skeleton,bindings,draft,composite,images=inputs(state,manifest,mesh['source_draft_sha256'],workspace)
    doc,scope=build_character(mesh,skeleton,bake,candidate,bindings,draft)
    scope['contact_report']=contacts(candidate,mesh,skeleton,bake,bindings,draft,images)
    data,scope=archive_document(doc,scope,candidate,images)
    return data,scope,(candidate,skeleton,mesh,bake,doc,scope,images,composite)


def read_character_preview(state,manifest,digest,*,workspace):
    saved=read_report(state,manifest['dataset_id'],'character-target-previews',digest)
    _,scope,_=build(state,manifest,saved['source_bake_sha256'],workspace)
    if canonical_sha256(saved)!=canonical_sha256(scope):raise ValueError('character_preview_mismatch')
    return saved


def execute(args):
    from .character_scene_view import render_scene
    manifest=read_input(args.manifest)
    digest=canonical_sha256(strict_json_object(read_real_file(args.bake,16<<20,'bake'),'bake'))
    data,scope,scene=build(args.state_root,manifest,digest,args.workspace)
    export_html(args.html,render_scene(*scene))
    export(args.zip,data)
    return scope,'character-target-previews',manifest['dataset_id'],0
