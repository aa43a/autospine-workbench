import {appendVisualScope} from '../modules/motion-visual-scope.js';
const artifact='a'.repeat(64),digest='b'.repeat(64),mesh='c'.repeat(64);
const regions={fixed:[],sliding:[],free:[],transition:[],occlusion:[0]};
const history=[{revision:1,slot:'sleeve',animation:'reach',action:'contact_scope',
  artifact_sha256:artifact,evidence_sha256:digest,event:{triangle:-1,time:0,reason:'user_visual_inspection',detected_failure:false},
  contact_scope:{mesh_sha256:mesh,reference_slot:'cape',regions},notes:'合成标注，仅用于测试'}];
const report={artifact_sha256:artifact,bones:['root'],slots:['sleeve','cape'],animations:[{name:'reach',duration:4}],
  rows:['sleeve','cape'].map(slot=>({slot,mesh_sha256:mesh,texture_path:`images/${slot}.png`,
    uvs:[0,0,1,0,1,1,0,1],triangles:[0,1,2,0,2,3]}))};
function state(){return {artifact_sha256:artifact,evidence_sha256:digest,revision:history.length,history:structuredClone(history),draft_sha256s:history.map((_,i)=>String(i+1).repeat(64))};}
window.fetch=async(url,options={})=>{
  let value;const path=String(url);
  if(path.endsWith('/partition-mesh.json')&&!options.method)value=report;
  else if(path.endsWith('/repair-draft')){
    if(options.method==='POST'){
      const body=JSON.parse(options.body);
      if(body.artifact_sha256!==artifact||body.expected_revision!==history.length||body.visual_inspection!==true||body.triangle!==-1)
        throw Error('测试请求身份或主动检查标记不正确');
      history.push({...body,revision:history.length+1,event:{triangle:-1,time:body.time,reason:'user_visual_inspection',detected_failure:false}});
      document.querySelector('#requests').textContent=JSON.stringify(body,null,2);
    }
    value=state();
  }else if(path.endsWith('/repair-execute')&&options.method==='POST'){
    document.querySelector('#requests').textContent=JSON.stringify({execution:JSON.parse(options.body),scope:history.at(-1).contact_scope},null,2);
    value={job_id:'diagnostic-only-no-server-job'};
  }else throw Error('隔离测试拒绝未声明请求：'+path);
  return {ok:true,json:async()=>structuredClone(value)};
};
// Image elements do not use window.fetch. Keep their synthetic pixels in this page too.
const NativeImage=window.Image,descriptor=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
window.Image=function(){const image=new NativeImage();Object.defineProperty(image,'src',{
  get(){return descriptor.get.call(image);},set(value){
    if(!String(value).includes('/images/'))throw Error('测试图片路径错误');
    descriptor.set.call(image,'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#8ac"/><path d="M20 20L180 180" stroke="white" stroke-width="20"/></svg>'));
  }});return image;};
appendVisualScope(document.querySelector('#app'),{job_id:'isolated-fixture',result:{artifact_sha256:artifact}},
  time=>document.querySelector('#requests').textContent=`定位 ${time} 秒（合成数据）`);
