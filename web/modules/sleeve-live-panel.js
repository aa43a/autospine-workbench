import {sleeveLivePoints, sleeveLiveAngles, drawSleeveTriangle} from './sleeve-live-model.js';

export function mountSleeveLive(root, candidate, images, bones, meshes) {
  if(!meshes)return {update(){}};
  const panel=root.querySelector('#sleeve-live');if(!panel)return {update(){}};
  panel.hidden=false;
  const canvas=panel.querySelector('canvas'),ctx=canvas.getContext('2d');
  const time=panel.querySelector('[data-time]'),play=panel.querySelector('[data-play]'),motion=panel.querySelector('[data-motion]');
  const compare=panel.querySelector('[data-compare]'),rigid=panel.querySelector('[data-rigid]'),wire=panel.querySelector('[data-wire]');
  const label=panel.querySelector('output'),status=panel.querySelector('[data-status]');
  let active=0,current=null,initial=null,playing=false,last=0,request=0,revision=0;
  const loaded=new Map();
  for(const [id,info] of Object.entries(images)){const image=new Image();image.onload=()=>schedule();image.onerror=()=>{status.textContent='贴图加载失败';};image.src=info.url;loaded.set(id,image);}
  function paint(){
    request=0;if(!current)return;
    const record=candidate.records[active],image=loaded.get(record.layer_id);if(!image?.complete||!image.naturalWidth)return;
    try{
      const box=images[record.layer_id].bbox,w=box[2]-box[0],h=box[3]-box[1];
      const assignments=(compare.checked?initial:current).records[active].assignments;
      const mesh=meshes.find(r=>r.layer_id===record.layer_id&&r.component_id===record.component_id)?.mesh;
      const points=sleeveLivePoints(record,assignments,bones,mesh,sleeveLiveAngles(Number(time.value),motion.value),rigid.checked);
      const scale=Math.min(canvas.width/(w*2),canvas.height/(h*1.6));
      ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.translate(canvas.width/2,canvas.height/2);ctx.scale(scale,scale);ctx.translate(-(box[0]+box[2])/2,-(box[1]+box[3])/2);
      for(const t of record.triangles){
        drawSleeveTriangle(ctx,image,t.map(v=>[record.vertices_xy[v][0]-box[0],record.vertices_xy[v][1]-box[1]]),t.map(v=>points[v]));
        if(wire.checked){ctx.beginPath();ctx.moveTo(...points[t[0]]);ctx.lineTo(...points[t[1]]);ctx.lineTo(...points[t[2]]);ctx.closePath();ctx.strokeStyle='#75d5ff80';ctx.lineWidth=.5;ctx.stroke();}
      }
      label.textContent=`${Number(time.value).toFixed(2)} / 2.00 秒`;
      status.textContent=`${compare.checked?'初始草稿':'当前标注'} · 即时更新 ${revision} · 不含袖口求解、碰撞和 Runtime QA`;
      canvas.dataset.revision=String(revision);canvas.dataset.previewTime=time.value;
    }catch(e){playing=false;play.textContent='播放';status.textContent=`预览失败：${e.message}`;}
  }
  function schedule(){if(!request)request=requestAnimationFrame(paint);}
  function tick(now){if(!playing)return;if(last)time.value=String((Number(time.value)+(now-last)/1000)%2);last=now;schedule();requestAnimationFrame(tick);}
  play.onclick=()=>{playing=!playing;play.textContent=playing?'暂停':'播放';last=0;if(playing)requestAnimationFrame(tick);};
  time.oninput=()=>{playing=false;play.textContent='播放';schedule();};
  panel.querySelector('[data-setup]').onclick=()=>{playing=false;play.textContent='播放';time.value='0';schedule();};
  for(const control of [motion,compare,rigid,wire])control.onchange=schedule;
  root.addEventListener('visibilitychange',()=>{if(root.hidden){playing=false;play.textContent='播放';}});
  return {update(index,draft,original){active=index;current=draft;initial=original;revision++;schedule();}};
}

