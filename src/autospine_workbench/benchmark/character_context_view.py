"""Single-canvas source context; fixed source layers never imply rigging authority."""
import base64
import json
from pathlib import Path
from ..targets.spine43.continuous_pose import world


def cards(source, atlas, doc, source_images, region_images):
    owners={p['id']:layer['layer_id'] for layer in atlas['layers'] for p in layer['partitions']}
    attachments=doc['skins'][0]['attachments']
    if set(owners)!=set(attachments):raise ValueError('context_partition_inventory')
    originals={r['layer_id']:r for r in source['layers']}
    if not set(owners.values()).issubset(originals):raise ValueError('context_source_layers')
    poses=[world(doc,i/30) for i in range(61)]
    result=[]
    image=lambda raw:'data:image/png;base64,'+base64.b64encode(raw).decode()
    for layer in source['layers']:
        name=layer['layer_id'];regions=[n for n in owners if owners[n]==name]
        if not regions:
            result.append(dict(name=name,kind='fixed_source_context',bbox=layer['bbox'],image=image(source_images[name])))
        for region in regions:
            attachment=attachments[region][region];w,h=attachment['width'],attachment['height']
            uv=attachment['uvs'];flat=attachment['triangles']
            result.append(dict(name=region,kind='animated_candidate',image=image(region_images[region]),
                               source=[[uv[i]*w,uv[i+1]*h] for i in range(0,len(uv),2)],
                               triangles=[flat[i:i+3] for i in range(0,len(flat),3)],
                               poses=[[[x,-y] for x,y in pose[region]] for pose in poses]))
    return result


def render(source, scene, report):
    data=json.dumps(dict(canvas=source['canvas'],cards=scene),ensure_ascii=False).replace('<','\\u003c')
    script=Path(__file__).with_name('elbow_bake_webgl.js').read_text('utf-8')+'\n'+Path(__file__).with_name('character_context_canvas.js').read_text('utf-8')
    return '<!doctype html><meta charset="utf-8"><style>body{font:17px system-ui;margin:24px;background:#eff2f5}canvas{height:70vh;max-width:95vw;background:repeating-conic-gradient(#ccc 0% 25%,white 0% 50%) 0/16px 16px}aside{padding:12px;background:#fff0cc}button,input{margin:12px}</style><h1>整角色上下文预览</h1><aside>静态原图层 + 当前四肢候选。静态层没有新增绑定；不是完整角色动画、官方Runtime或生产验收。源图层顺序未复核。</aside><p>'+str(report['fixed_source_layer_count'])+' 个静态来源图层；'+str(report['animated_partition_count'])+' 个动画分区；'+str(report['residual_visible_pixels'])+' 个残余像素未进入该动画场景。</p><button id="play">播放／暂停</button><input id="time" type="range" min="0" max="60" value="0"><output id="stamp">0s</output><label><input id="context" type="checkbox" checked>显示静态来源上下文</label><div><canvas id="scene"></canvas></div><p id="error"></p><script id="data" type="application/json">'+data+'</script><script>'+script+'</script>'
