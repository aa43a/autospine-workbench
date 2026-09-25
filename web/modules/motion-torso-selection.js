// Optional visual bake; changing source resets the experimental choice.
export function createTorsoSelection(anchor){
  const label=document.createElement('label');
  const input=document.createElement('input');input.type='checkbox';input.disabled=true;
  label.append(input,document.createTextNode(' 躯干投影偏斜（实验）'));
  const mode=document.createElement('select');mode.setAttribute('aria-label','躯干投影参照');
  mode.add(new Option('以所选视角首帧为参照','torso-plane-compensated-deform-v1-experiment'));
  const reference=new Option('以源动作 0° 首帧为正面素材参照','reference-torso-plane-compensated-deform-v1-experiment');
  reference.disabled=true;mode.add(reference);label.append(mode);
  const hint=document.createElement('p');hint.className='hint';
  hint.textContent='根据双肩与骨盆调整躯干，并补偿头部和手臂。正面参照会保留偏转后的宽度缩短，假设源动作 0° 首帧与正面素材对应。结果烘焙到网格，骨骼辅助线保持原位置；不补全侧背面。暂不能与“区域深度排序”同时使用。';
  anchor.before(label,hint);let available=false,source=null;
  function update(){input.disabled=!(available&&source);if(input.disabled)input.checked=false;mode.disabled=!input.checked;}
  input.onchange=update;
  return {available(value,referenceAvailable=false){available=value;reference.disabled=!referenceAvailable;update();},
    source(value){if(source?.job_id!==value?.job_id){input.checked=false;mode.selectedIndex=0;}source=value;update();},
    selection(depth,projection){
      if(!input.checked||input.disabled)return {};
      if(depth.depth_review_profile==='external-regional-depth-order-v1')throw Error('请先取消区域深度排序，再构建躯干投影候选。');
      if(mode.value===reference.value&&!projection)throw Error('正面参照躯干投影需要先选择明确的动作偏转角。');
      return {torso_projection_profile:mode.value};
    }};
}
