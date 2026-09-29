import test from 'node:test';
import assert from 'node:assert/strict';
import '../tools/character-framebuffer-stats.js';

const stats=globalThis.autospineFramebufferStats;
function original(pixels,width,height){
  let visible=0,border=0;
  for(let y=0;y<height;y++)for(let x=0;x<width;x++)if(pixels[(y*width+x)*4+3]>=8){
    visible++;if(x===0||y===0||x===width-1||y===height-1)border++;
  }
  return {visible,border};
}

test('counts exactly the same threshold and border pixels for small and one-pixel surfaces',()=>{
  for(let width=1;width<=8;width++)for(let height=1;height<=8;height++){
    const pixels=new Uint8Array(width*height*4);
    for(const alpha of [0,7,8,255]){
      pixels.fill(254);for(let i=3;i<pixels.length;i+=4)pixels[i]=alpha;
      assert.deepEqual(stats(pixels,width,height),original(pixels,width,height));
    }
    // Place one visible pixel at every position: corners and 1px dimensions
    // must never be double-counted; interior pixels must never count as border.
    pixels.fill(0);
    for(let alpha=3;alpha<pixels.length;alpha+=4){
      pixels[alpha]=8;
      assert.deepEqual(stats(pixels,width,height),original(pixels,width,height));
      pixels[alpha]=0;
    }
  }
});

test('preserves full-frame counts for patterned character-size RGBA buffers',()=>{
  for(const [width,height] of [[1014,1306],[640,960]]){
    const pixels=new Uint8Array(width*height*4);
    for(let i=0;i<pixels.length;i++)pixels[i]=(i*73+i%17)%256;
    assert.deepEqual(stats(pixels,width,height),original(pixels,width,height));
  }
});

test('rejects mismatched framebuffer dimensions instead of ignoring pixels',()=>{
  for(const [width,height] of [[0,1],[1,0],[1.5,2],[-1,1],[1,2]]){
    assert.throws(()=>stats(new Uint8Array(4),width,height),/framebuffer_stats_dimensions/);
  }
});
