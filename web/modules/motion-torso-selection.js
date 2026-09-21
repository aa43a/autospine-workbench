// Optional visual bake; changing source resets the experimental choice.
export function createTorsoSelection(anchor){
  const label=document.createElement('label');
  const input=document.createElement('input');input.type='checkbox';input.disabled=true;
  label.append(input,document.createTextNode(' 躯干投影偏斜（实验）'));
  const hint=document.createElement('p');hint.className='hint';
  hint.textContent='根据双肩与骨盆调整躯干，并补偿头部和手臂。结果烘焙到网格，骨骼辅助线保持原位置；不补全侧背面。暂不能与“区域深度排序”同时使用。';
  anchor.before(label,hint);let available=false,source=null;
  function update(){input.disabled=!(available&&source);if(input.disabled)input.checked=false;}
  return {available(value){available=value;update();},
    source(value){if(source?.job_id!==value?.job_id)input.checked=false;source=value;update();},
    selection(depth){
      if(!input.checked||input.disabled)return {};
      if(depth.depth_review_profile==='external-regional-depth-order-v1')throw Error('请先取消区域深度排序，再构建躯干投影候选。');
      return {torso_projection_profile:'torso-plane-compensated-deform-v1-experiment'};
    }};
}
