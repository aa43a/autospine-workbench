"""Stable setup slot reorder: wing attachments behind every other local attachment."""
from copy import deepcopy
from hashlib import sha256
import json
from .wing_spine_preview import encode
from ..resolved_project import canonical_sha256


def reorder(doc,back):
    result=deepcopy(doc);slots=result['slots'];names=[s['name'] for s in slots]
    if len(names)!=len(set(names)) or not set(back).issubset(names):raise ValueError('back_order_slot_inventory')
    if any('drawOrder' in a or 'draworder' in a for a in result.get('animations',{}).values()):raise ValueError('back_order_animated_order_requires_review')
    result['slots']=[s for s in slots if s['name'] in back]+[s for s in slots if s['name'] not in back]
    return result


def build(source,files):
    if source['schema']!='autospine.wing-split-preview/v1' or source['authority']!='none' or source['production_authorized'] is not False:raise ValueError('back_order_source')
    if set(files)!=set(source['files']) or any(sha256(files[n]).hexdigest()!=d for n,d in source['files'].items()):raise ValueError('back_order_files')
    doc=json.loads(files['skeleton.json']);back={r['id'] for r in source['regions'] if r['id'].startswith('wing-')}
    if not back or 'topwear' not in {s['name'] for s in doc['slots']}:raise ValueError('back_order_scope')
    changed=reorder(doc,back);outputs=dict(files);outputs['skeleton.json']=encode(changed)
    outputs['editor/skeleton.json']=encode(reorder(json.loads(files['editor/skeleton.json']),back))
    report=deepcopy(source);report.update(schema='autospine.wing-back-order-preview/v1',profile='stable-wing-back-setup-order-v1',
      source_split_preview_sha256=canonical_sha256(source),slot_order_change=dict(before=[s['name'] for s in doc['slots']],after=[s['name'] for s in changed['slots']]),
      textures_unchanged=True,rig_and_motion_unchanged=True,draw_order_scope='wing_and_topwear_subset_only')
    outputs['README.txt']+=b'\nWing and residual slots now precede topwear (back-to-front). Textures, bones and animation are unchanged. Local subset only; source wing pixels in topwear remain.\n'
    outputs['review.html']=f'''<!doctype html><meta charset="utf-8"><title>主翼后置层序候选</title><style>body{{font:18px/1.7 system-ui;max-width:1000px;margin:40px auto;color:#243448}}</style>
<h1>主翼后置：只修改层序</h1><p>翼片与翼片残余已放到上衣后方，内部次序不变。保留此前11笔清理，未采用主翼删除遮罩。</p>
<p>由后至前：{' → '.join(report['slot_order_change']['after'])}</p>
<p><a href="preview.zip">下载候选包</a> · <a href="preview-manifest.json">来源报告</a></p><p>骨骼、动画、纹理和UV不变。本次仅为翼片／上衣局部包，不能替代完整角色层序验收。上衣本身的翼片像素仍可能造成遮挡和重影。</p>'''.encode()
    report['files']={n:sha256(raw).hexdigest() for n,raw in outputs.items()};outputs['preview-manifest.json']=encode(report)
    return report,outputs


def verify(saved,source,files):
    expected,_=build(source,files)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('back_order_replay')
    return deepcopy(saved)
