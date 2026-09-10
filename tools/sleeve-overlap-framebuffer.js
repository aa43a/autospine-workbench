/* Same-pose triangle isolation uses the official renderer, preserving full-mesh order. */
window.installSleeveOverlap=({canvas,gl,skeleton,renderer,left,bottom})=>{
  window.captureOverlap=(animation,index,pair)=>{
    const pose=window.captureFrame(animation,index),slot=skeleton.slots[0],a=slot.appliedPose.attachment;
    const original=a.triangles;
    if(!Array.isArray(pair)||pair.length!==2||pair[0]===pair[1]||pair.some(i=>!Number.isInteger(i)||i<0||3*i+2>=original.length))throw Error('overlap_pair');
    const vertices=new Float32Array(a.worldVerticesLength);
    a.computeWorldVertices(skeleton,slot,0,vertices.length,vertices,0,2);
    const ids=pair.flatMap(i=>Array.from(original.slice(3*i,3*i+3)));
    const x0=Math.max(0,Math.floor(Math.min(...ids.map(i=>vertices[2*i])))-left-3);
    const y0=Math.max(0,Math.floor(Math.min(...ids.map(i=>vertices[2*i+1])))-bottom-3);
    const x1=Math.min(canvas.width,Math.ceil(Math.max(...ids.map(i=>vertices[2*i])))-left+3);
    const y1=Math.min(canvas.height,Math.ceil(Math.max(...ids.map(i=>vertices[2*i+1])))-bottom+3);
    const width=x1-x0,height=y1-y0;
    if(width<=0||height<=0||width*height>1000000)throw Error('overlap_roi');
    const render=triangles=>{
      a.triangles=triangles;gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
      renderer.begin();renderer.drawSkeleton(skeleton);renderer.end();
      const raw=new Uint8Array(width*height*4);gl.readPixels(x0,y0,width,height,gl.RGBA,gl.UNSIGNED_BYTE,raw);
      if(gl.getError()!==gl.NO_ERROR)throw Error('overlap_readback');
      const image=document.createElement('canvas');image.width=width;image.height=height;
      const ctx=image.getContext('2d'),pixels=ctx.createImageData(width,height);
      // Raw WebGL output is premultiplied; unpremultiply for a normal PNG image.
      for(let y=0;y<height;y++)for(let x=0;x<width;x++){
        const src=(y*width+x)*4,dst=((height-1-y)*width+x)*4,alpha=raw[src+3];
        for(let k=0;k<3;k++)pixels.data[dst+k]=alpha?Math.min(255,Math.round(raw[src+k]*255/alpha)):0;
        pixels.data[dst+3]=alpha;
      }
      ctx.putImageData(pixels,0,0);return {raw,png:image.toDataURL('image/png')};
    };
    try{
      const first=Array.from(original.slice(pair[0]*3,pair[0]*3+3)),second=Array.from(original.slice(pair[1]*3,pair[1]*3+3));
      const omit=id=>Array.from(original).filter((_,i)=>Math.floor(i/3)!==id);
      const ordered=pair.slice().sort((x,y)=>x-y).flatMap(i=>Array.from(original.slice(i*3,i*3+3)));
      const images={full:render(original),first:render(first),second:render(second),pair:render(ordered),
        without_first:render(omit(pair[0])),without_second:render(omit(pair[1]))};
      const dual=[];let maxAlphaIncrease=0,maxFullChange=0;
      for(let i=0;i<width*height;i++){
        const off=i*4,aa=images.first.raw[off+3],ab=images.second.raw[off+3];
        if(aa<8||ab<8)continue;
        const alphaIncrease=images.pair.raw[off+3]-Math.max(aa,ab);
        let change=0;
        for(let k=0;k<4;k++)for(const mode of ['without_first','without_second'])change=Math.max(change,Math.abs(images.full.raw[off+k]-images[mode].raw[off+k]));
        maxAlphaIncrease=Math.max(maxAlphaIncrease,alphaIncrease);maxFullChange=Math.max(maxFullChange,change);
        dual.push({world_xy:[left+x0+i%width+.5,bottom+y0+Math.floor(i/width)+.5],first_alpha:aa,second_alpha:ab,
          composite_rgba:Array.from(images.full.raw.slice(off,off+4)),alpha_increase:alphaIncrease,max_premultiplied_channel_change:change});
      }
      return {animation,index,time:pose.time,pair,roi:{x:left+x0,y:bottom+y0,width,height},
        dual_alpha8_pixels:dual.length,max_alpha_increase:maxAlphaIncrease,max_full_channel_change:maxFullChange,
        dual_samples:dual,images:Object.fromEntries(Object.entries(images).map(([k,v])=>[k,v.png]))};
    }finally{a.triangles=original;window.captureFrame(animation,index);}
  };
};
