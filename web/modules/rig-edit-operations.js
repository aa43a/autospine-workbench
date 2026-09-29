// Shared, atomic editing protocol. The output remains the existing export contract.
import {normalizeLayerEdits} from './motion-layer-transform.js';
const fields=['dx','dy','rotation','scaleX','scaleY'];
const defaults=slot=>({slot,dx:0,dy:0,rotation:0,scaleX:1,scaleY:1});
const pointer=value=>String(value).replaceAll('~','~0').replaceAll('/','~1');
export function layerEditImpact(value){
  const edits=normalizeLayerEdits(value);
  return {slots:edits.transforms.map(row=>row.slot),geometry:edits.transforms.length>0,
    draw_order:edits.draw_order.length>0,execution:'full_build',
    checks:edits.transforms.length?['geometry','contact','occlusion','runtime']:edits.draw_order.length?['occlusion','runtime']:[]};
}
export function layerEditImpactText(value){
  const impact=layerEditImpact(value);
  if(!impact.checks.length)return '没有图层修改。';
  return `${impact.geometry?`${impact.slots.length} 个图层需复核变形、接触和遮挡`:'绘制顺序需复核遮挡'}；正式构建仍执行完整检查。可用顶部撤销／重做恢复修改。`;
}
export function applyRigEditOperations(value,operations,{layers=null}={}){
  // Never modify caller-owned state, including on a failure late in a batch.
  const original=structuredClone(value),known=layers?.map(layer=>layer.slot);
  let next,index=-1,slot=null,path='';
  try{
    next=normalizeLayerEdits(value,known);
    if(!Array.isArray(operations)||operations.length>256)throw Error('修改批次无效');
    for(index=0;index<operations.length;index++){
      const operation=operations[index];slot=operation?.slot??null;path=`/operations/${index}`;
      if(!operation||typeof operation!=='object'||Array.isArray(operation))throw Error('修改操作无效');
      const allowed={transform:['op','slot','values'],reset:['op','slot'],order:['op','slots'],replace:['op','value']}[operation.op];
      if(!allowed||Object.keys(operation).length!==allowed.length||!allowed.every(key=>Object.hasOwn(operation,key)))throw Error('修改操作或字段不支持');
      if(['transform','reset'].includes(operation.op)){
        path=`/layers/${pointer(slot)}`;
        if(typeof slot!=='string'||!slot||known&&!known.includes(slot))throw Error('图层不存在，请重新加载对应角色版本');
        if(operation.op==='transform'){
          if(layers&& !layers.find(layer=>layer.slot===slot)?.supported)throw Error('此图层暂不支持位置校正');
          const values=operation.values;
          if(!values||typeof values!=='object'||Array.isArray(values)||Object.keys(values).some(key=>!fields.includes(key)))throw Error('图层属性不支持');
          const row={...(next.transforms.find(row=>row.slot===slot)??defaults(slot))};
          for(const [key,number] of Object.entries(values)){
            path=`/layers/${pointer(slot)}/${key}`;
            const [low,high]=key.startsWith('scale')?[.05,20]:key==='rotation'?[-3600,3600]:[-4096,4096];
            if(!Number.isFinite(number)||number<low||number>high)throw Error(`${key} 必须在 ${low} 至 ${high} 之间`);
            row[key]=number;
          }
          next.transforms=next.transforms.filter(row=>row.slot!==slot);
          if(fields.some(key=>row[key]!==defaults(slot)[key]))next.transforms.push(row);
        }else next.transforms=next.transforms.filter(row=>row.slot!==slot);
      }else if(operation.op==='order')next.draw_order=structuredClone(operation.slots);
      else next=normalizeLayerEdits(operation.value,known);
      next=normalizeLayerEdits(next,known);
      if(layers)for(const row of next.transforms){
        if(!layers.find(layer=>layer.slot===row.slot)?.supported){slot=row.slot;path=`/layers/${pointer(slot)}`;throw Error('此图层暂不支持位置校正');}
      }
    }
    return {ok:true,value:next,diagnostics:[],inverse:[{op:'replace',value:normalizeLayerEdits(value,known)}],impact:layerEditImpact(next)};
  }catch(error){return {ok:false,value:original,diagnostics:[{severity:'error',code:'rig_edit_rejected',operation:index,slot,path,message:error.message,hint:'本批次未生效；调整所指图层或属性后重试。'}]};}
}
