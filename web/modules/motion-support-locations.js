// Exact-candidate locations from saved readiness evidence; never infer missing times.
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const candidate=/^\/api\/motions\/motion-[a-f0-9]{32}\/view\/(?:related-candidates\/[a-f0-9]{64}\/)?player\.html$/;
const reports=new Set(['player.html','contact.html','depth.html','report.json']);
export function stageLocationsHTML(stage,base,playerPath){
  if(!candidate.test(playerPath))return '';
  const root=playerPath.slice(0,-'player.html'.length);
  const detail=reports.has(stage.href)?`<a href="${escape(base+root+stage.href)}" target="_blank" rel="noopener">查看此候选检查</a>`:'';
  const rows=Array.isArray(stage.failures)?stage.failures:[];
  const reasons=Array.isArray(stage.reasons)?stage.reasons:[];
  if(!rows.length&&!reasons.length)return stage.status==='sampled_pass'?'':detail;
  return `<details><summary>已记录的异常定位 · ${rows.length} 条</summary>`+
    '<p>仅列出报告提供的样本，不表示全部失败帧；未提供时刻的项目不推算时间。</p>'+detail+
    (reasons.length?`<p>${reasons.map(escape).join('；')}</p>`:'')+
    '<ul>'+rows.map(row=>{
      const time=row.time,valid=typeof time==='number'&&Number.isFinite(time)&&time>=0;
      const position=valid?`<a href="${escape(base+playerPath+'?time='+encodeURIComponent(time))}" target="_blank" rel="noopener">${time.toFixed(3)} 秒</a>`:'未提供有效时刻';
      const location=[row.slot,row.bone,row.joint,row.reason_code||row.reason].filter(v=>typeof v==='string').map(escape).join(' · ');
      return `<li>${position}${location?' · '+location:''}</li>`;
    }).join('')+'</ul></details>';
}
