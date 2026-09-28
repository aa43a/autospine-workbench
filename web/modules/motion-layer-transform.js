// Whole-clip attachment corrections in Spine world coordinates, after skinning.
export function editableLayer(document,slot){
  const choices=document.skins?.[0]?.attachments?.[slot],attachment=choices?.[slot];
  return Boolean(choices&&Object.keys(choices).length===1&&attachment?.type==='mesh'&&Array.isArray(attachment.vertices)&&Array.isArray(attachment.uvs)&&attachment.vertices.length!==attachment.uvs.length);
}
export function layerBounds(points){
  if(!points.length)return null;
  let left=Infinity,right=-Infinity,bottom=Infinity,top=-Infinity;
  for(let i=0;i<points.length;i+=2){left=Math.min(left,points[i]);right=Math.max(right,points[i]);bottom=Math.min(bottom,points[i+1]);top=Math.max(top,points[i+1]);}
  return {left,right,bottom,top,width:right-left,height:top-bottom};
}
export function transformLayerVertices(points,edit,pivot){
  if(!edit)return Array.from(points);
  const angle=edit.rotation*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle);
  const result=[];
  for(let i=0;i<points.length;i+=2){const x=(points[i]-pivot[0])*edit.scaleX,y=(points[i+1]-pivot[1])*edit.scaleY;
    result.push(pivot[0]+edit.dx+c*x-s*y,pivot[1]+edit.dy+s*x+c*y);}
  return result;
}
export function normalizeLayerEdits(value,slots=null){
  if(value==null)return {profile:'slot-world-affine-v1',transforms:[],draw_order:[]};
  const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(key=>Object.hasOwn(v,key));
  const validSlot=slot=>typeof slot==='string'&&slot.length>0&&slot.length<=256;
  if(!exact(value,['profile','transforms','draw_order'])||value.profile!=='slot-world-affine-v1'||!Array.isArray(value.transforms)||!Array.isArray(value.draw_order)||value.transforms.length>256||value.draw_order.length>256)throw Error('图层校正格式无效');
  const known=slots?new Set(slots):null,seen=new Set();
  const transforms=value.transforms.map(edit=>{
    if(!exact(edit,['slot','dx','dy','rotation','scaleX','scaleY'])||!validSlot(edit.slot)||known&&!known.has(edit.slot)||seen.has(edit.slot))throw Error('图层校正包含未知或重复图层');seen.add(edit.slot);
    const row={slot:edit.slot};for(const key of ['dx','dy','rotation','scaleX','scaleY']){
      if(!Number.isFinite(edit[key]))throw Error('图层校正数值无效');row[key]=edit[key];}
    if(Math.abs(row.dx)>4096||Math.abs(row.dy)>4096||Math.abs(row.rotation)>3600||row.scaleX<.05||row.scaleX>20||row.scaleY<.05||row.scaleY>20)throw Error('图层校正超出范围：位移 ±4096，旋转 ±3600°，缩放 0.05–20');return row;
  });
  const order=value.draw_order;
  if(new Set(order).size!==order.length||order.some(slot=>!validSlot(slot))||known&&order.length&&(order.length!==slots.length||order.some(slot=>!known.has(slot))))throw Error('图层顺序必须包含全部图层且不重复');
  return {profile:value.profile,transforms,draw_order:[...order]};
}
export function pointInLayer(point,vertices,triangles){
  for(let i=0;i<triangles.length;i+=3){const a=triangles[i]*2,b=triangles[i+1]*2,c=triangles[i+2]*2;
    const ax=vertices[a],ay=vertices[a+1],bx=vertices[b],by=vertices[b+1],cx=vertices[c],cy=vertices[c+1];
    const det=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy);if(Math.abs(det)<1e-10)continue;
    const u=((by-cy)*(point.x-cx)+(cx-bx)*(point.y-cy))/det;
    const v=((cy-ay)*(point.x-cx)+(ax-cx)*(point.y-cy))/det;
    if(u>=-1e-7&&v>=-1e-7&&u+v<=1+1e-7)return true;
  }return false;
}
// The displayed canvas is letterboxed with object-fit: contain.
export function canvasContentRect(rect,width,height){
  const scale=Math.min(rect.width/width,rect.height/height);
  return {left:rect.left+(rect.width-width*scale)/2,top:rect.top+(rect.height-height*scale)/2,width:width*scale,height:height*scale,scale};
}
export function canvasWorldPoint(x,y,rect,bounds){
  const box=canvasContentRect(rect,bounds.width,bounds.height);
  if(box.scale<=0||x<box.left||y<box.top||x>box.left+box.width||y>box.top+box.height)return null;
  return {x:bounds.left+(x-box.left)/box.scale,y:bounds.bottom+bounds.height-(y-box.top)/box.scale};
}
