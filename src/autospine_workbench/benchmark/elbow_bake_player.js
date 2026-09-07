"use strict";
const cards = JSON.parse(document.getElementById("data").textContent);
const frame = document.getElementById("frame"), wire = document.getElementById("wire");
let playing = false, last = 0;
for (const card of cards) {
  const article = document.createElement("article"), title = document.createElement("h2");
  title.textContent = card.name;
  const summary = document.createElement("p");
  summary.textContent = `${card.status} · 最小面积 ${(card.qa.min_area_ratio*100).toFixed(1)}% · 插值误差 ${card.qa.max_interpolation_error_px.toFixed(3)}px`;
  card.canvas = document.createElement("canvas"); card.canvas.width=680;card.canvas.height=600;
  article.append(title,summary,card.canvas);document.getElementById("cards").append(article);
  const points=card.poses.flat();
  card.bounds=[Math.min(...points.map(p=>p[0]))-10,Math.min(...points.map(p=>p[1]))-10,
    Math.max(...points.map(p=>p[0]))+10,Math.max(...points.map(p=>p[1]))+10];
  card.texture=new Image();card.texture.onload=draw;card.texture.src=card.image;
}
if(!cards.length)document.getElementById("cards").textContent="没有已选 Mesh，未生成动画。";
function draw(){
  document.getElementById("position").textContent=frame.value;
  for(const card of cards){
    if(!card.texture.complete||!card.texture.naturalWidth)continue;
    try{
      if(!card.render)card.render=textureRenderer(card.canvas,card.texture);
      card.render(card,card.poses[Number(frame.value)],wire.checked);
    }catch(error){card.canvas.replaceWith(document.createTextNode("纹理预览不可用："+error.message));}

  }
}
frame.oninput=draw;wire.onchange=draw;
document.getElementById("play").onclick=()=>{playing=!playing;document.getElementById("play").textContent=playing?"暂停":"播放";last=0;};
function tick(time){
  if(playing){
    if(!last)last=time;
    const steps=Math.floor((time-last)*30/1000);
    if(steps){frame.value=(Number(frame.value)+steps)%60;draw();last+=steps*1000/30;}
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
