// Optional versioned strategy; changing source cannot silently retain it.
export function createDepthSelection(anchor) {
  const label=document.createElement('label');
  const input=document.createElement('input'); input.type='checkbox'; input.disabled=true;
  label.append(input,document.createTextNode(' 区域深度排序（实验）'));
  const hint=document.createElement('p'); hint.className='hint';
  hint.textContent='适用于 FBX/BVH：根据已有裙装记录拆分绘制区域并检查前后关系。保留纹理与权重；冲突时保留原顺序。Kimodo NPZ 暂不支持此策略。';
  anchor.before(label,hint);
  let available=false,source=null;
  function update(){
    input.disabled=!(available && source && ['bvh','fbx'].includes(source.format));
    if(input.disabled)input.checked=false;
  }
  return {
    available(value){available=value;update();},
    source(value){if(source?.job_id!==value?.job_id)input.checked=false;source=value;update();},
    selection(){return input.checked&&!input.disabled?{depth_review_profile:'external-regional-depth-order-v1'}:{};},
  };
}
