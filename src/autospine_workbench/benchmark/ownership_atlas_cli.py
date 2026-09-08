"""Compile and replay isolated ownership tiles, without granting target authority."""
import argparse
import hashlib
import json
from pathlib import Path
from html import escape
from ..asset.joints.ownership_atlas import build
from ..resolved_project import canonical_sha256
from .artifacts import read_input
from .shared_partition_cli import compile_report as source_report
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import archive,export
from .mapping_cli import export_html
from .semantic_view import _image_url


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved.get('schema')!='autospine.layer-partitions/v2':raise ValueError('ownership_atlas_source_invalid')
    expected,_,sources=source_report(state,manifest,saved['source_mesh_sha256'],workspace)
    if canonical_sha256(expected)!=digest:raise ValueError('ownership_atlas_source_mismatch')
    layers=[];files={}
    for layer in saved['layers']:
        result,page=build(sources[layer['texture_ref']],sources[layer['ownership_ref']],layer)
        layers.append(result);files[result['page_ref']]=page
    doc={'schema':'autospine.ownership-atlas/v1','profile':'isolated-ownership-tiles-linear-v1',
        'authority':'none','production_authorized':False,'source_partitions_sha256':digest,
        'source_skeleton_sha256':saved['source_skeleton_sha256'],'layers':layers,
        'files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()},
        'runtime_status':'not_evaluated','seam_status':'not_evaluated'}
    files['ownership-atlas.json']=json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    data=archive(files)
    if len(data)>32<<20:raise ValueError('ownership_atlas_archive_too_large')
    doc['zip_sha256']=hashlib.sha256(data).hexdigest()
    return doc,data,files


def read_atlas(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_,_=compile_report(state,manifest,saved['source_partitions_sha256'],workspace)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('ownership_atlas_replay_mismatch')
    return saved


def render(doc,files):
    cards=[]
    for layer in doc['layers']:
        source=_image_url(files[layer['page_ref']],doc['files'][layer['page_ref']]);w,h=layer['page_size'];rects=[]
        for tile in layer['tiles']:
            x,y,tw,th=tile['rect'];color={1:'#16a3a0',2:'#d16621',3:'#dc318a'}[tile['owner_code']]
            rects.append(f'<rect x="{x}" y="{y}" width="{tw}" height="{th}" stroke="{color}" stroke-width="2" fill="none"/>')
        cards.append(f'<article><h2>{escape(layer["layer_id"])} · {w}×{h}</h2><p>一张纹理页：青框左区、橙框右区、粉框残余。残余仍未绑定。</p>'
            f'<svg viewBox="0 0 {w} {h}"><image href="{source}" width="{w}" height="{h}"/>{"".join(rects)}</svg>'
            '<p>逐像素重建与透明隔离边通过。权重和网格几何不变，UV已改为纹理页坐标。</p></article>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+\
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'">'+\
        '<title>分区采样隔离</title><style>body{max-width:1200px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f5f7fa;color:#233548}article{background:white;padding:20px;margin:20px 0}svg{width:100%;max-height:650px}.notice{background:#fff0cc;padding:16px}</style>'+\
        '<h1>共享纹理页 · 分区采样隔离</h1><p class="notice">分区掩码已经烘焙到派生纹理，原图与ownership工件保持不变。验证范围仅限level-0线性过滤、无mipmap、固定UV；'+\
        '不是原始源PNG的原位共享，也不是Spine运行包。目标Adapter、变形、接缝和官方Runtime尚未通过。</p>'+''.join(cards)+'</html>'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','partitions','html','output','zip'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        manifest=read_input(args.manifest)
        doc,data,files=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.partitions)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],doc)
        export_mesh(args.output,doc);export(args.zip,data);export_html(args.html,render(doc,files))
        print(json.dumps({'status':'written','artifact_sha256':digest,'pages':len(doc['layers']),'authority':'none'}));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'ownership_atlas_request_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
