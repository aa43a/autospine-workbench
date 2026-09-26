export const fixedLegReason='motion_final_leg_fixed_vertices_infeasible';
const node=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};

export function appendRepairBlocker(parent,job){
  if(job.status!=='failed'||job.reason_code!==fixedLegReason)return;
  const button=node('button','查看固定区域限制'),status=node('section','');
  status.setAttribute('aria-live','polite');parent.append(button,status);
  button.onclick=async()=>{
    button.disabled=true;status.textContent='正在读取限制与原动作位置…';
    try{
      const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/view/repair-blocker.json`,{cache:'no-store'});
      const report=await response.json();
      if(!response.ok)throw Error(report.reason_code||'读取失败');
      if(report.job_id!==job.job_id||report.reason_code!==fixedLegReason||report.candidate_generated!==false)throw Error('失败报告身份不匹配');
      status.replaceChildren(node('p',`${report.slot}：${report.failed_triangles} 个固定三角形存在面积超限。在 ${report.sample_count} 个采样时刻检查中记录 ${report.failure_observations} 次超限；重复时刻不计为不同三角形。`),
        node('p','这些顶点在当前局部策略中不可移动，因此没有生成新候选。重复执行同一策略不能消除限制；需调整投影、绑定区域或姿态表达。此结论不表示必须补图。'));
      for(const row of report.examples){
        const p=node('p',`三角形 ${row.triangle} · ${row.time.toFixed(3)} 秒 · 原始面积比 ${row.setup_ratio.toFixed(3)} · 投影面积比 ${row.projected_ratio.toFixed(3)}。 `);
        const link=node('a','在原候选定位');link.href=`/api/motions/${encodeURIComponent(report.parent_job_id)}/view/player.html?time=${row.time}`;
        p.append(link);status.append(p);
      }
      status.append(node('p','每个三角形只展示最严重采样，最多展示 24 个；未列出的区域与原始证据保留。'));
      const link=node('a','返回原候选选择处理方式');link.href='/motions.html#'+encodeURIComponent(report.parent_job_id);status.append(link);
    }catch(error){status.textContent='无法读取限制：'+error.message;}
    finally{button.disabled=false;}
  };
}
