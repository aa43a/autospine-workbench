"""Render CPU alpha-support diagnostics, not character appearance previews."""
import json


def write(output,rows):
    data=json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><meta charset="utf-8"><title>同帧遮挡冲突定位</title>
<style>body{background:#14212c;color:#eaf2f7;font:16px system-ui;margin:24px}button,select,input{font:inherit}
.images{display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap}.images img{max-width:48vw;max-height:65vh;object-fit:contain}
pre{white-space:pre-wrap}#seek{width:65vw}a{color:#87ccff}</style>
<h1>同帧遮挡冲突定位</h1><p>这是 CPU alpha 覆盖诊断，不是官方 Runtime 截图。
不同颜色代表循环中的区域；白色表示全部区域在同一像素有 alpha≥8 的覆盖。</p>
<p>共同覆盖支持“当前顺序约束在局部互相矛盾”，不证明哪条深度推断正确，也不等于最终画面出现错误。</p>
<label>异常时刻 <select id="frame"></select></label><p><input id="seek" type="range" min="0" step="1"></p>
<div id="status"></div><div id="legend"></div><pre id="detail"></pre><div class="images"><img id="full" alt="区域覆盖范围"><img id="zoom" alt="共同覆盖附近放大图"></div>
<p><a href="report.json">完整来源与诊断记录</a></p><script>
const rows=DATA,select=document.querySelector('#frame'),seek=document.querySelector('#seek');
const labels={simultaneous_cycle_support:'同位置约束循环',spatially_distributed_cycle_support:'不同位置形成循环',cycle_not_simultaneous_at_sample:'本时刻未同时支持全部循环边',unmeasured:'未完成测量'};
rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${r.time.toFixed(6)}s · ${labels[r.status]||r.status}`;select.append(o)});
seek.max=Math.max(0,rows.length-1);function show(i){const r=rows[i];if(!r)return;select.value=i;seek.value=i;
document.querySelector('#status').textContent=`${i+1}/${rows.length} · 同位置覆盖 ${r.common_pixels??'未测'} 像素`;
const legend=document.querySelector('#legend');legend.replaceChildren();r.slots.forEach((s,j)=>{const tag=document.createElement('span');tag.textContent=' ■ '+s+' ';tag.style.color=['#46a0f5','#5ac87d','#f07d41','#c85ad7'][j%4];legend.append(tag)});
document.querySelector('#detail').textContent=r.slots.join(' → ')+' → '+r.slots[0]+'\\n'+r.edges.map((e,j)=>`${e.back} → ${e.front}：${e.source}；同帧覆盖 ${r.edge_overlap_pixels?.[j]??'未测'}`).join('\\n');
for(const k of ['full','zoom']){const img=document.querySelector('#'+k);img.hidden=!r[k];if(r[k])img.src=r[k];else img.removeAttribute('src')}}
select.onchange=()=>show(Number(select.value));seek.oninput=()=>show(Number(seek.value));show(0);
</script>'''.replace('DATA',data)
    (output/'index.html').write_text(page,encoding='utf-8')


def image(output,index,row,visual):
    import numpy as np
    from PIL import Image
    masks,common=visual;palette=[[70,160,245],[90,200,125],[240,125,65],[200,90,215]]
    rgb=np.full((*common.shape,3),28,dtype=np.uint8)
    for i,m in enumerate(masks):rgb[m]=palette[i%len(palette)]
    rgb[common]=[255,255,255]
    full=Image.fromarray(rgb);name=f'cycle-{index:03d}.png';full.save(output/name);row['full']=name
    box=row['common_raster_bbox']
    if box:
        x,y,w,h=box;left,top,width,height=row['roi']
        crop=full.crop((max(0,x-left-8),max(0,y-top-8),min(width,x-left+w+8),min(height,y-top+h+8)))
        name=f'cycle-{index:03d}-zoom.png';crop.resize((crop.width*4,crop.height*4),Image.Resampling.NEAREST).save(output/name)
        row['zoom']=name
