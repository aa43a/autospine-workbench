/* Optional diagnostic hook: official parser, pose and renderer remain in charge. */
window.installLocalFramebuffer=({canvas,gl,renderer,shared,isolated,pose})=>{
 window.captureLocal=({time,point,names,mode,scale,atlas})=>{
  if(![1,4].includes(scale)||!['driver','follower','pair','all'].includes(mode)||!['shared','reference'].includes(atlas))throw Error('invalid_probe');
  const item=atlas==='shared'?shared:isolated;
  const left=Math.floor(point[0])-16,bottom=Math.floor(point[1])-16;
  const previous={width:canvas.width,height:canvas.height,x:renderer.camera.position.x,y:renderer.camera.position.y,w:renderer.camera.viewportWidth,h:renderer.camera.viewportHeight};
  try{
   canvas.width=canvas.height=32*scale;
   renderer.camera.setViewport(32,32);renderer.camera.position.x=left+16;renderer.camera.position.y=bottom+16;renderer.camera.update();
   pose(item,time);
   const allowed=mode==='driver'?[names[0]]:mode==='follower'?[names[1]]:names;
   for(const slot of item.skeleton.slots)if(mode!=='all'&&!allowed.includes(slot.data.name))slot.appliedPose.attachment=null;
   gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
   renderer.begin();renderer.drawSkeleton(item.skeleton);renderer.end();
   const raw=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,raw);
   if(gl.getError()!==gl.NO_ERROR)throw Error('local_framebuffer_error');
   const rgba=[];const x0=(Math.floor(point[0])-left)*scale,y0=(Math.floor(point[1])-bottom)*scale;
   for(let y=0;y<scale;y++)for(let x=0;x<scale;x++){const i=((y0+y)*canvas.width+x0+x)*4;rgba.push(Array.from(raw.slice(i,i+4)));}
   const output=document.createElement('canvas');output.width=canvas.width;output.height=canvas.height;
   const ctx=output.getContext('2d'),pixels=ctx.createImageData(output.width,output.height);
   for(let y=0;y<output.height;y++)for(let x=0;x<output.width;x++){
    const i=(y*output.width+x)*4,j=((output.height-1-y)*output.width+x)*4,a=raw[j+3];
    // Convert premultiplied framebuffer RGB for the straight-alpha PNG view only.
    for(let c=0;c<3;c++)pixels.data[i+c]=a?Math.min(255,Math.round(raw[j+c]*255/a)):0;
    pixels.data[i+3]=a;
   }
   ctx.putImageData(pixels,0,0);
   return {time,point,names,mode,scale,atlas,world_rect:[left,bottom,32,32],rgba,
    gl_attributes:gl.getContextAttributes(),blend:[gl.getParameter(gl.BLEND_SRC_RGB),gl.getParameter(gl.BLEND_DST_RGB),gl.getParameter(gl.BLEND_SRC_ALPHA),gl.getParameter(gl.BLEND_DST_ALPHA)],
    image:output.toDataURL('image/png')};
  }finally{
   canvas.width=previous.width;canvas.height=previous.height;renderer.camera.setViewport(previous.w,previous.h);
   renderer.camera.position.x=previous.x;renderer.camera.position.y=previous.y;renderer.camera.update();pose(item,0);
  }
 };
};
