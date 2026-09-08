/* Framebuffer visibility evidence; hiding a residual is not a crack detector. */
globalThis.limbResidualMetrics=(full,without,width,height)=>{
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||
     full.length!==width*height*4||without.length!==full.length)throw Error('residual_pixel_shape');
  let changed=0,anyChanged=0,exposed=0,alphaChanged=0,minX=width,minY=height,maxX=-1,maxY=-1;
  for(let i=0;i<full.length;i+=4){
    let delta=0;
    for(let c=0;c<4;c++)delta=Math.max(delta,Math.abs(full[i+c]-without[i+c]));
    if(delta>0)anyChanged++;
    if(full[i+3]>=8&&without[i+3]<8)exposed++;
    if(Math.abs(full[i+3]-without[i+3])>1)alphaChanged++;
    if(delta<=1)continue;
    changed++;
    const p=i/4,x=p%width,y=Math.floor(p/width);
    minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);
  }
  return {changed_pixels:changed,any_channel_changed_pixels:anyChanged,alpha_changed_pixels:alphaChanged,
    pixels_exposed_by_hiding:exposed,changed_rect_bottom_left:changed?[minX,minY,maxX-minX+1,maxY-minY+1]:null};
};
