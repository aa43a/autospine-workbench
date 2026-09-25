export const MOVING_ANKLE_PROFILE='moving-source-ankle-timeline-v1';
export function ankleSelection(enabled,body){
  if(!enabled)return {};
  if(body.clip!=null)throw Error('跟随源脚端目前需要完整动作，请取消裁剪。');
  return {moving_ankle_profile:MOVING_ANKLE_PROFILE,contact_correction:false};
}
export function createAnkleSelection(button,contact){
  const label=document.createElement('label');
  const input=document.createElement('input');input.type='checkbox';input.disabled=true;
  label.append(input,'跟随源动作脚端（实验）');
  const note=document.createElement('p');note.className='hint';
  note.textContent='保留源动作中脚的移动，联合调整身体与腿部；启用后接触只检查、不锁脚。失败会保留原动画并报告异常。需要完整动作，暂不能与接触后修正并用。';
  button.before(label,note);
  let previous=contact.checked;
  input.onchange=()=>{
    if(input.checked){previous=contact.checked;contact.checked=false;contact.disabled=true;}
    else{contact.checked=previous;contact.disabled=false;}
  };
  return {available(value){input.disabled=!value;},selection:body=>ankleSelection(input.checked,body),
    reset(){if(input.checked){input.checked=false;input.onchange();}}};
}
