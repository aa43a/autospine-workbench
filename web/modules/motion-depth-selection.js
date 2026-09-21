// Optional versioned strategy; changing source cannot silently retain it.
export function createDepthSelection(anchor) {
  const label=document.createElement('label');
  const input=document.createElement('input'); input.type='checkbox'; input.disabled=true;
  label.append(input,document.createTextNode(' 区域深度排序（实验）'));
  const hint=document.createElement('p'); hint.className='hint';
  hint.textContent='适用于 FBX/BVH/Kimodo SOMA77：根据已有裙装记录拆分绘制区域并检查前后关系。保留纹理与权重；冲突时保留原顺序。Kimodo 中间时刻使用已记录的三维位置线性插值，不代表真实布料深度。';
  const sparseLabel=document.createElement('label'),sparse=document.createElement('input');
  sparse.type='checkbox';sparse.disabled=true;
  sparseLabel.append(sparse,document.createTextNode(' 稀疏遮挡采样（实验）'));
  const sparseHint=document.createElement('p');sparseHint.className='hint';
  sparseHint.textContent='跳过网格不可能重叠的空白块，保留像素精度与计算预算。支持 FBX/BVH/Kimodo，可与躯干偏斜组合；暂不能与区域深度排序组合。';
  anchor.before(label,hint,sparseLabel,sparseHint);
  let available=false,sparseAvailable=false,source=null;
  function update(){
    input.disabled=!(available && source && ['bvh','fbx','npz'].includes(source.format));
    if(input.disabled)input.checked=false;
    sparse.disabled=!(sparseAvailable&&source);if(sparse.disabled)sparse.checked=false;
  }
  return {
    available(value,other=false){available=value;sparseAvailable=other;update();},
    source(value){if(source?.job_id!==value?.job_id){input.checked=false;sparse.checked=false;}source=value;update();},
    selection(){
      if(input.checked&&sparse.checked)throw Error('请只选择一种遮挡策略：区域深度排序或稀疏遮挡采样。');
      if(sparse.checked&&!sparse.disabled)return {depth_review_profile:'external-arm-torso-depth-sparse-v1-experiment'};
      return input.checked&&!input.disabled?{depth_review_profile:'external-regional-depth-order-v1'}:{};
    },
  };
}
