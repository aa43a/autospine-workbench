"use strict";
// Rasterize shared triangle edges once; canvas clip antialiasing leaves false seam lines.
function textureRenderer(canvas,image){
  const gl=canvas.getContext("webgl",{alpha:true,antialias:false,premultipliedAlpha:false});
  if(!gl)throw new Error("WebGL unavailable");
  function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error("Shader failed");return s;}
  const program=gl.createProgram();
  gl.attachShader(program,shader(gl.VERTEX_SHADER,"attribute vec2 p; attribute vec2 uv; varying vec2 tex; void main(){gl_Position=vec4(p,0.,1.);tex=uv;}"));
  gl.attachShader(program,shader(gl.FRAGMENT_SHADER,"precision mediump float; varying vec2 tex; uniform sampler2D image; uniform bool wire; void main(){gl_FragColor=wire?vec4(0.,.8,.6,1.):texture2D(image,tex);}"));
  gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error("Link failed");
  gl.useProgram(program);
  const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);
  gl.enable(gl.BLEND);gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
  const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
  for(const [name,offset] of [["p",0],["uv",8]]){const loc=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,16,offset);}
  const wireLocation=gl.getUniformLocation(program,"wire");
  return function(card,points,showWire){
    const [x,y,r,b]=card.bounds,scale=Math.min(660/(r-x),580/(b-y));
    const ox=(680-(r-x)*scale)/2,oy=(600-(b-y)*scale)/2;
    function vertex(i){const p=points[i],s=card.source[i];return [2*(ox+(p[0]-x)*scale)/680-1,1-2*(oy+(p[1]-y)*scale)/600,s[0]/image.naturalWidth,s[1]/image.naturalHeight];}
    gl.viewport(0,0,680,600);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform1i(wireLocation,0);
    const triangles=card.triangles.flatMap(t=>t.flatMap(vertex));
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(triangles),gl.DYNAMIC_DRAW);gl.drawArrays(gl.TRIANGLES,0,triangles.length/4);
    if(showWire){const lines=card.triangles.flatMap(([a,b,c])=>[a,b,b,c,c,a].flatMap(vertex));gl.uniform1i(wireLocation,1);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(lines),gl.DYNAMIC_DRAW);gl.drawArrays(gl.LINES,0,lines.length/4);}
  };
}
