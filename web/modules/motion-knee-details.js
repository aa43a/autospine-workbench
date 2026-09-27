import {kneeLabels,kneeRows,strongestKnee} from './motion-knee-model.js';

function node(tag,text){const el=document.createElement(tag);el.textContent=text;return el;}

export function appendKneeDetails(container,base,artifact,onSeek){
  const button=document.createElement('button');button.textContent='检查膝盖方向与深度';
  const panel=document.createElement('section');panel.setAttribute('aria-label','膝部动作与素材需求');container.append(button,panel);
  button.onclick=async()=>{
    button.disabled=true;panel.textContent='正在比较同帧骨轴…';
    try{
      const response=await fetch(base+'bend-status.json',{cache:'no-store'}),report=await response.json();
      if(!response.ok)throw Error(report.reason_code||'读取失败');
      const rows=kneeRows(report,artifact);
      panel.replaceChildren();
      const note=document.createElement('p');note.textContent='仅检查源采样时刻的骨轴。深度符号不是人体朝前方向；方向一致也不能证明膝形或裙腿遮挡正确。';panel.append(note);
      for(const side of ['left','right']){
        const counts={};for(const r of rows.filter(r=>r.side===side))counts[r.status]=(counts[r.status]||0)+1;
        panel.append(node('p',(side==='left'?'左腿':'右腿')+'：'+Object.entries(counts).map(([k,v])=>`${kneeLabels[k]} ${v}`).join('；')));
        const loss=rows.filter(r=>r.side===side&&r.hiddenBend!==null&&r.hiddenBend>=30);
        if(loss.length){
          const worst=loss.reduce((a,b)=>a.hiddenBend>=b.hiddenBend?a:b);
          const jump=node('button',`${side==='left'?'左腿':'右腿'}：${loss.length} 个采样弯曲损失 ≥30°，定位最大值 ${worst.time.toFixed(3)} 秒`);
          jump.onclick=()=>{sideSelect.value=worst.side;reset();slider.value=String(selected.findIndex(r=>r.time===worst.time));render();onSeek(worst.time);};
          panel.append(jump);
        }
      }
      const side=node('select','');side.setAttribute('aria-label','检查哪条腿');
      const sideSelect=side;
      for(const [value,label] of [['left','左腿'],['right','右腿']]){const option=node('option',label);option.value=value;side.append(option);}
      side.value=rows[strongestKnee(rows)].side;
      let selected=rows.filter(r=>r.side===side.value);
      const slider=node('input','');slider.type='range';slider.min='0';slider.step='1';slider.setAttribute('aria-label','膝部源采样时间');
      const output=node('p',''),issues=node('p',''),seek=node('button','在当前时间轴定位'),next=node('button','下一处需要检查的采样');
      const current=()=>selected[Number(slider.value)];
      function render(){
        const r=current(),s=r.source;
        output.textContent=`${r.time.toFixed(3)} 秒 · ${kneeLabels[r.status]}`;
        if(Number.isFinite(r.source_time)&&r.source_time!==r.time)output.textContent+=` · 原动作 ${r.source_time.toFixed(3)} 秒`;
        if(s.status==='measured')output.textContent+=` · 三维弯曲 ${s.bend_degrees.toFixed(1)}° · 大腿/小腿投影长度 ${s.projection_visibility.map(v=>(v*100).toFixed(1)+'%').join(' / ')} · 弯曲平面与画面平行程度 ${s.screen_plane_alignment==null?'未测量':(s.screen_plane_alignment*100).toFixed(1)+'%'}`;
        if(Object.hasOwn(s,'projected_bend_degrees'))output.textContent+=` · 源二维弯曲 ${s.projected_bend_degrees==null?'不可观测':s.projected_bend_degrees.toFixed(1)+'°'} · 深度中损失 ${r.hiddenBend==null?'不可观测':r.hiddenBend.toFixed(1)+'°'}`;
        if(r.target?.status==='measured')output.textContent+=` · 当前二维弯曲 ${r.target.bend_degrees.toFixed(1)}°`;
        issues.textContent=r.issues.join('；')||'该采样未触发方向或强缩短提示，仍需检查实际贴图。';
        next.disabled=!selected.some(r=>r.issues.length);
      }
      function reset(){selected=rows.filter(r=>r.side===side.value);slider.max=String(selected.length-1);slider.value=String(strongestKnee(selected));render();}
      side.onchange=reset;slider.oninput=render;seek.onclick=()=>onSeek(current().time);
      next.onclick=()=>{const index=Number(slider.value);for(let step=1;step<=selected.length;step++){const i=(index+step)%selected.length;if(selected[i].issues.length){slider.value=String(i);render();onSeek(current().time);break;}}};
      panel.append(side,slider,output,issues,seek,next,node('p','先在同一时刻比较源正侧视和角色。30° 仅用于定位明显投影损失，不是验收门槛。骨轴正确但轮廓仍失败时，检查姿态替换或补图需求；这些提示不会自动认定缺素材、裁剪动作或放宽网格门槛。'));
      reset();
    }catch(error){panel.textContent='无法检查：'+error.message;}finally{button.disabled=false;}
  };
}
