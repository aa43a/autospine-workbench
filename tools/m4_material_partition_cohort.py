"""Compare one proximal partition rule across fixed structures, without adoption."""
import argparse
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image

from autospine_workbench.automation.animated_store import AnimatedStore
from m4_root_material import partition


def run(source_root, field_root, output):
    output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for index,name in enumerate(('alice','huiye','hongmeiling')):
        source=source_root/str(index)
        receipt=json.loads((source/'report.json').read_bytes())
        field_raw=(field_root/(name+'.json')).read_bytes()
        field=json.loads(field_raw)
        digest=receipt['candidate_bundle_sha256']
        if field['candidate']!=digest:
            raise ValueError('partition_cohort_source_mismatch')
        files=AnimatedStore(source/'isolated-store').read(digest)
        document=json.loads(files['skeleton.json'])
        arm,body=field['arm'],field['body']
        slots=[s['name'] for s in document['slots']]
        if slots.index(arm)>=slots.index(body):
            raise ValueError('setup_occlusion_order_not_supported')
        folder=output/name;folder.mkdir()
        attachment=document['skins'][0]['attachments'][arm][arm]
        original=files['images/'+attachment.get('path',arm)+'.png']
        (folder/'source.png').write_bytes(original)
        row=dict(character=name,candidate=digest,arm=arm,body=body,
                 source_texture_sha256=sha256(original).hexdigest(),
                 depth_field_sha256=sha256(field_raw).hexdigest(),authority='none',selected=False)
        try:
            root,free,evidence=partition(document,files,arm,body,'upperarm_r','forearm_r')
        except ValueError as error:
            if str(error)!='root_material_support_missing':raise
            row.update(status='no_proximal_setup_support',root_visible_texels=0)
        else:
            image=np.asarray(Image.open(BytesIO(original)).convert('RGBA'))
            # A selected region is a proposal, not evidence of a semantic garment seam.
            root_mask=root[:,:,3]>=8
            np.testing.assert_array_equal(np.maximum(root[:,:,3],free[:,:,3]),image[:,:,3])
            for label,value in [('root',root),('free',free)]:
                Image.fromarray(value).save(folder/(label+'.png'))
            yy,xx=np.nonzero(root_mask)
            row.update(status='candidate_requires_structure_review',evidence=evidence,
                source_visible_texels=int((image[:,:,3]>=8).sum()),root_visible_texels=int(root_mask.sum()),
                root_bounds=[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],
                rules=dict(root='setup_occlusion_proposal_keep_behind_body',
                           free='depth_driven_only_where_observable_else_unresolved'))
        rows.append(row)
    report=dict(profile='three_structure_proximal_partition-review-v1',rows=rows,authority='none',selected=False)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    sections=[]
    for row in rows:
        name=row['character'];panels=[]
        for label,title in [('source','源图'),('root','近端候选：固定后置假设'),('free','其余区域：仍需深度证据')]:
            if (output/name/(label+'.png')).exists():
                panels.append(f'<figure><img src="{name}/{label}.png"><figcaption>{title}</figcaption></figure>')
        status={'candidate_requires_structure_review':'初始遮挡候选，结构归属尚未确定',
                'no_proximal_setup_support':'没有近端初始遮挡依据'}[row['status']]
        sections.append(f'<section><h2>{escape(name)}</h2><p>{status} · 近端可见采样 {row["root_visible_texels"]}</p><div>{"".join(panels)}</div></section>')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>三结构肩部材料分区</title>'
        '<style>body{background:#17232e;color:white;font:16px sans-serif}section div{display:flex;align-items:flex-start}figure{margin:12px}img{max-width:28vw;max-height:600px;background:repeating-conic-gradient(#34414d 0% 25%,#26323d 0% 50%) 0/20px 20px}p{max-width:1100px}</style>'
        '<h1>同一规则的三结构材料分区</h1><p>近端选择仅证明 setup 遮挡和距离支持，不等于识别服装接缝；其余区域不自动视为深度已知。本页没有改动候选、权重或验收。</p>'+''.join(sections),encoding='utf8')
    print(json.dumps([{k:r.get(k) for k in ('character','status','source_visible_texels','root_visible_texels','root_bounds')} for r in rows]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source_root','field_root','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.source_root,args.field_root,args.output)
