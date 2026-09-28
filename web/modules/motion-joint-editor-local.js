import {JOINT_LOCAL_LIMITS} from './motion-joint-editor-state.js';
const names={strength:'摆动强度',stiffness:'回弹刚度',damping:'阻尼',max_angle:'最大角度 / °',root_fraction:'发根固定比例'};
const steps={strength:.05,stiffness:1,damping:.05,max_angle:.25,root_fraction:.01};
const node=(tag,text)=>{const element=document.createElement(tag);if(text)element.textContent=text;return element;};
export function createJointLocalOptions({container,group,meta,change}){
  const regions=(meta.inventory?.[group]??[]).filter(row=>row.state==='available');
  if(!regions.length)return {update(){}};
  let current=null;const fields=new Map();
  const panel=node('details');panel.className='joint-local';panel.append(node('summary','局部响应参数（可选）'));
  panel.append(node('p','默认继承本组参数。只为异常区域覆盖参数；恢复后继续随全组调整。'));
  const label=node('label','响应区域'),select=node('select');select.setAttribute('aria-label',`${group} 局部响应区域`);
  for(const region of regions){const option=node('option',region.name||region.slot);option.value=region.slot;select.append(option);}label.append(select);panel.append(label);
  for(const [key,bounds]of Object.entries(JOINT_LOCAL_LIMITS)){
    if(group==='cloth'&&key==='root_fraction')continue;
    const label=node('label',names[key]),input=node('input');input.type='number';input.min=bounds[0];input.max=bounds[1];input.step=steps[key];
    input.setAttribute('aria-label',`${group} 局部${names[key]}`);fields.set(key,input);label.append(input);panel.append(label);
  }
  const status=node('p');status.className='joint-note';
  const apply=node('button','应用局部参数'),reset=node('button','恢复此区域全组参数');apply.type=reset.type='button';
  const inherited=key=>current?.[group]?.[key]??(key==='root_fraction'?regions.find(row=>row.slot===select.value).root_fraction??.35:undefined);
  function render(){
    if(!current)return;const custom=current[group].overrides?.[select.value]??{};
    for(const [key,input]of fields)if(document.activeElement!==input)input.value=custom[key]??inherited(key);
    const selected=current[group].slots;
    status.textContent=`${Object.keys(custom).length?'已覆盖局部参数':'使用全组参数'}${selected?.length&&!selected.includes(select.value)?' · 当前未选择此区域参与响应':''}`;
  }
  apply.onclick=()=>{const values={};for(const [key,input]of fields){const v=input.value===''?NaN:Number(input.value);if(v!==inherited(key))values[key]=v;}change(group,select.value,values);};
  reset.onclick=()=>change(group,select.value,null);select.onchange=render;
  panel.append(status,apply,reset);container.append(panel);
  return {update(config,busy=false){current=config;render();for(const input of panel.querySelectorAll('input,select,button'))input.disabled=busy;}};
}
