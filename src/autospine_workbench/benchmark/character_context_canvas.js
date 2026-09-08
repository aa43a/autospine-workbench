// Existing diagnostic WebGL mesh rasterizer avoids Canvas triangle clip seams.
const data=JSON.parse(document.querySelector('#data').textContent),canvas=document.querySelector('canvas');
canvas.width=680;canvas.height=600;const ctx=canvas.getContext('2d');
const slider=document.querySelector('#time'),toggle=document.querySelector('#context');
const [width,height]=data.canvas,scale=Math.min(660/width,580/height),ox=(680-width*scale)/2,oy=(600-height*scale)/2;
function draw(){
 const frame=Number(slider.value);ctx.clearRect(0,0,680,600);
 for(const card of data.cards){
  if(card.kind==='fixed_source_context'){
   if(toggle.checked){const [x,y,r,b]=card.bbox;ctx.drawImage(card.loaded,ox+x*scale,oy+y*scale,(r-x)*scale,(b-y)*scale);}continue;
  }
  card.render(card,card.poses[frame],false);ctx.drawImage(card.surface,0,0);
 }
 document.querySelector('#stamp').textContent=(frame/30).toFixed(2)+'s';
}
let playing=false,last=0;
Promise.all(data.cards.map(card=>new Promise((resolve,reject)=>{
 const image=new Image();image.onload=()=>{try{
  card.loaded=image;
  if(card.kind==='animated_candidate'){
   card.surface=document.createElement('canvas');card.surface.width=680;card.surface.height=600;
   card.bounds=[0,0,width,height];card.render=textureRenderer(card.surface,image);
  }
  resolve();
 }catch(error){reject(error);}};image.onerror=reject;image.src=card.image;
}))).then(()=>{draw();window.ready=true;}).catch(()=>{document.querySelector('#error').textContent='图层加载失败';window.failure=true;});
slider.oninput=()=>{if(window.ready)draw();};toggle.onchange=()=>{if(window.ready)draw();};
document.querySelector('#play').onclick=()=>{playing=!playing;last=0;};
function tick(now){if(playing&&window.ready){if(!last)last=now;const n=Math.floor((now-last)*30/1000);if(n){slider.value=(Number(slider.value)+n)%61;last+=n*1000/30;draw();}}requestAnimationFrame(tick);}requestAnimationFrame(tick);
