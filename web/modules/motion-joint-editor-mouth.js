const node=(tag,text)=>{const element=document.createElement(tag);if(text)element.textContent=text;return element;};
export async function readJointMouthAsset(file){
  if(file.size>32768)throw Error('PNG 不得超过 32 KB。');
  const bytes=new Uint8Array(await file.arrayBuffer());
  if(bytes.length<33||[137,80,78,71,13,10,26,10].some((v,i)=>bytes[i]!==v))throw Error('请上传 PNG 图片。');
  const header=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  if(header.getUint32(16)!==64||header.getUint32(20)!==48)throw Error('嘴部模板需要 64 × 48 像素。');
  if(bytes[24]!==8||bytes[25]!==6||bytes[28]!==0)throw Error('请导出 8-bit RGBA、非交错的透明 PNG。');
  for(let offset=8;offset+12<=bytes.length;){const size=header.getUint32(offset);
    if(String.fromCharCode(...bytes.slice(offset+4,offset+8))==='acTL')throw Error('请上传单帧 PNG，不支持 APNG 动画。');offset+=12+size;}
  let bitmap;try{bitmap=await createImageBitmap(file);}catch{throw Error('PNG 无法解码，请重新导出图片。');}
  const canvas=new OffscreenCanvas(64,48),context=canvas.getContext('2d');context.drawImage(bitmap,0,0);bitmap.close();
  const rgba=context.getImageData(0,0,64,48).data;let visible=false,transparent=false;
  for(let i=3;i<rgba.length;i+=4){visible ||= rgba[i]>=8;transparent ||= rgba[i]<255;}
  if(!visible||!transparent)throw Error('图片需要同时包含可见嘴部和透明背景。');
  const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
  return {png_base64:btoa(String.fromCharCode(...bytes)),sha256:[...digest].map(v=>v.toString(16).padStart(2,'0')).join('')};
}
export function createJointMouthAsset({container,change}){
  let epoch=0,disposed=false,reading=false,busy=false,current=null;
  const panel=node('details');panel.className='joint-mouth-asset';panel.append(node('summary','替换基础开口图片（可选）'));
  panel.append(node('p','可上传 64 × 48 像素、32 KB 以内的单帧透明 PNG（8-bit RGBA、非交错），覆盖程序开口模板。仍需启用上方模板开关并重新构建。原嘴部图层保留；此图片不是音素同步。'));
  const label=node('label','嘴部透明 PNG'),input=node('input');input.type='file';input.accept='image/png';label.append(input);
  const status=node('p');status.setAttribute('role','status');status.className='joint-note';
  const preview=node('img');preview.alt='当前开口替换图';preview.width=128;preview.height=96;preview.hidden=true;
  const reset=node('button','清除上传，恢复程序模板');reset.type='button';
  const disabled=()=>{input.disabled=busy||reading;reset.disabled=busy||(!current&&!reading);};
  input.onchange=async()=>{
    const file=input.files?.[0];if(!file)return;const id=++epoch;reading=true;disabled();status.textContent='正在读取嘴部图片…';
    try{const image=await readJointMouthAsset(file);if(disposed||id!==epoch)return;change(image);status.textContent=`已载入 ${file.name}。构建时还会检查透明区域和 PNG 内容。`;}
    catch(error){if(!disposed&&id===epoch)status.textContent=error.message;}
    finally{if(!disposed&&id===epoch){reading=false;input.value='';disabled();}}
  };
  reset.onclick=()=>{epoch++;reading=false;input.value='';change(null);status.textContent='已恢复程序模板，重新构建后生效。';disabled();};
  panel.append(label,preview,status,reset);container.append(panel);
  return {update(config,blocked=false){busy=blocked;current=config.face.mouth.template_image??null;preview.hidden=!current;
    if(current){const src=`data:image/png;base64,${current.png_base64}`;if(preview.src!==src)preview.src=src;
      if(!reading)status.textContent=`已保存替换图 · SHA-256 ${current.sha256.slice(0,12)}…${config.face.mouth.template_enabled?'':' · 模板开关尚未启用'}`;}
    else if(!reading)status.textContent='使用程序模板；未上传替换图片。';disabled();},
    dispose(){disposed=true;epoch++;panel.remove();}};
}
