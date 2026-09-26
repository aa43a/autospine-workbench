import {collectSupportSnapshot} from './motion-support-snapshot.js';
import {supportReportHTML,supportTotals} from './motion-support-report.js';
const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
export function appendSupportExport(parent,pack){
  const section=node('section'),title=node('h3','支持范围报告'),start=node('button','核对并生成支持范围报告');
  const stop=node('button','停止生成');stop.disabled=true;
  const status=node('p','汇总全部固定组合、阶段结论、独立改进与替代视角，不受上方筛选影响。读取已有证据，不重新捕获动画。');status.setAttribute('role','status');
  const files=node('p');section.append(title,start,stop,status,files);parent.append(section);
  let version=0,controller,urls=[];
  function clear(){for(const url of urls)URL.revokeObjectURL(url);urls=[];files.replaceChildren();}
  function invalidate(message){version++;controller?.abort();clear();start.disabled=false;stop.disabled=true;status.textContent=message;}
  start.onclick=async()=>{
    const token=++version;controller?.abort();controller=new AbortController();clear();start.disabled=true;stop.disabled=false;
    try{
      const snapshot=await collectSupportSnapshot(pack,async(path,signal)=>{
        const response=await fetch(path,{cache:'no-store',signal}),value=await response.json();
        if(!response.ok)throw Error(value.reason_code||'读取失败');return value;
      },{signal:controller.signal,onProgress:p=>{if(token===version)status.textContent=`已完成 ${p.finished}/${p.total} · ${p.label} · ${p.phase}。`;}});
      if(token!==version)return;
      const html=supportReportHTML(snapshot,location.origin),totals=supportTotals(snapshot);
      for(const [ext,raw,mime,label] of [['html',html,'text/html','下载可阅读报告'],['json',JSON.stringify(snapshot,null,2),'application/json','下载完整证据快照']]){
        const url=URL.createObjectURL(new Blob([raw],{type:mime}));urls.push(url);
        const a=node('a',label);a.href=url;a.download=`m4-support-${snapshot.plan_sha256.slice(0,12)}.${ext}`;files.append(a,'　');
      }
      status.textContent=`报告已生成：固定组合 ${totals.expected} 项，身份核对 ${totals.verified} 项，有效阶段接受 ${totals.accepted} 项。读取失败和缺失项保留；此快照不会自动更新。`;
    }catch(error){if(token===version)status.textContent='报告未生成：'+error.message;}
    finally{if(token===version){start.disabled=false;stop.disabled=true;}}
  };
  stop.onclick=()=>invalidate('已停止生成，未提供不完整下载。可以重新核对。');
  for(const name of ['motion-stage-review-saved','motion-related-review-saved'])window.addEventListener(name,()=>
    invalidate('阶段结论已更新，请重新生成报告；此前下载的文件保留为历史快照。'));
  window.addEventListener('pagehide',()=>{version++;controller?.abort();clear();},{once:true});
}
