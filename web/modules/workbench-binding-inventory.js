const NAMES={upperarm:'上臂',forearm:'前臂',hand:'手',thigh:'大腿',calf:'小腿',foot:'脚',head:'头部',chest:'胸部',pelvis:'骨盆',root:'根骨骼'};
export function boneLabel(name){
  const match=/^(upperarm|forearm|hand|thigh|calf|foot)_([lr])$/.exec(name);
  if(match)return `${match[2]==='l'?'左':'右'}${NAMES[match[1]]}`;
  return NAMES[name]||(name.startsWith('cloth-')?'衣料辅助骨':name);
}
export function bindingInventoryRows(document,inventory,layerId){
  if(inventory?.schema!=='autospine.weighted-binding-inventory/v1'||inventory.authority!=='none')return [];
  return inventory.regions.filter(r=>r.layer_id===layerId).map(region=>{
    const row=document.createElement('div'),summary=document.createElement('p'),detail=document.createElement('details'),title=document.createElement('summary');
    summary.textContent=`${region.region_id} → ${region.influences.map(b=>boneLabel(b.bone)).join(' + ')}`;
    title.textContent=`实际顶点权重 · ${region.vertex_count} 个顶点`;detail.append(title);
    for(const bone of region.influences){
      const line=document.createElement('p');line.textContent=`${boneLabel(bone.bone)}：影响 ${bone.vertex_count} 个顶点，非零权重 ${(bone.min_weight*100).toFixed(1)}%–${(bone.max_weight*100).toFixed(1)}%`;
      line.setAttribute('title',bone.bone);detail.append(line);
    }
    const note=document.createElement('p');note.textContent='来自当前导出网格；权重大小不是语义正确率。';detail.append(note);
    row.append(summary,detail);return row;
  });
}
