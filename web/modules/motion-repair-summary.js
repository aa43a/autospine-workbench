import {geometryLines} from './motion-repair-geometry.js';
import {switchContinuityLines} from './motion-switch-continuity.js';
import {garmentSummary} from './motion-garment-follow.js';
export async function appendRepairSummary(panel,job) {
  if(!job.result?.repair_profile)return;
  const section=document.createElement('section');panel.append(section);
  section.textContent='正在读取局部修正对照…';
  try {
    const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/view/repair-summary.json`,{cache:'no-store'});
    const report=await response.json();
    if(!response.ok||report.artifact_sha256!==job.result.artifact_sha256)throw Error('修正结果身份不匹配');
    section.replaceChildren();const title=document.createElement('h4');title.textContent=report.garment_follow?'裙腰跟随候选前后':report.additional_view?'新视角附件候选前后':report.region_order?'区域顺序候选':report.pose_geometry?'姿态修形候选前后':report.material?'区域换图候选前后':report.boundary?'分区候选前后':'局部修正前后';section.append(title);
    if(report.garment_follow)for(const text of garmentSummary(report.garment_follow)){
      const p=document.createElement('p');p.textContent=text;section.append(p);
    }
    if(report.local_solver){const p=document.createElement('p');
      p.textContent='自动策略：在最终腿姿态上同时约束原始与投影面积。固定单骨顶点、权重和其他附件保持不变；原候选与修正候选使用同一组时间采样比较。';section.append(p);
    }
    for(const [label,geometry] of [['原候选',report.before],['修正候选',report.after]]) {
      if(report.region_order&&label==='修正候选') {
        const names=new Set(report.region_order.regions.map(r=>r.slot)),rows=geometry.records.filter(r=>names.has(r.slot)),p=document.createElement('p');
        p.textContent=`修正候选：${rows.length} 个区域动作记录，${rows.filter(r=>!r.passed).length} 个仍有几何超限。仅修改绘制顺序，不会消除原有变形失败。`;section.append(p);continue;
      }
      for(const text of geometryLines(label,geometry,report.slot)) {
        const p=document.createElement('p');p.textContent=text;section.append(p);
      }
    }
    const note=document.createElement('p');note.textContent=report.local_solver
      ?'同一时间采样上的对照只证明已执行的几何检查。接触和遮挡需要重新检查，视觉尚未接受。'
      :'新候选保留原检查时刻并增加修正关键点与中点；采样数可能不同，失败次数不能直接当作错误率比较。骨骼与其他附件保持不变，遮挡和视觉尚未重新接受。';
    const link=document.createElement('a');link.textContent='查看原候选';link.href='/motions.html#'+encodeURIComponent(report.parent_job_id);
    section.append(note,link);
    if(report.additional_view) {
      const v=report.additional_view,p=document.createElement('p');
      p.textContent=`新附件 ${v.variant_attachment} 在 ${v.interval.map(t=>Number(t.toFixed(6))).join('–')} 秒启用（含起点、不含终点），区间外恢复 ${v.original_attachment}。上方分别显示原附件和新附件的检查；任一附件失败均保留。切换边界、纹理接缝和整体动作仍需复核。`;
      section.append(p);
      for(const text of switchContinuityLines(v.switch_continuity)){
        const line=document.createElement('p');line.textContent=text;section.append(line);
      }
      for(const time of v.runtime_interval) {
        const a=document.createElement('a');a.textContent=`检查切换边界 ${time.toFixed(6)} 秒 `;
        a.href=`/api/motions/${encodeURIComponent(job.job_id)}/view/player.html?time=${time}`;section.append(a);
      }
    }
    if(report.region_order){const p=document.createElement('p'),r=report.region_order;
      p.textContent=`${r.selected_triangles.length} 个选中三角形，${r.interval?`${r.interval[0]}–${r.interval[1]} 秒（含起点、不含终点），区间外恢复原顺序`:'整段'}位于 ${r.reference_slot} ${r.side==='after'?'前方':'后方'}。权重、纹理与运动保留；区域内无用顶点已移除。视觉接缝仍需复核。`;section.append(p);
    }
    if(report.pose_geometry){const p=document.createElement('p'),g=report.pose_geometry;
      p.textContent=`显式修形：${g.vertices} 个选区顶点，${g.times.length} 个关键姿态，区间 ${g.interval[0]}–${g.interval[1]} 秒。纹理、UV 和骨骼保持原样；补丁插值不代表整段轮廓通过。`;section.append(p);
      for(const time of g.times){const a=document.createElement('a');a.textContent=`查看 ${time.toFixed(3)} 秒姿态 `;
        a.href=`/api/motions/${encodeURIComponent(job.job_id)}/view/player.html?time=${time}`;section.append(a);}
    }
    if(report.material){const p=document.createElement('p'),m=report.material;
      p.textContent=`已对 ${m.selected_triangles.length} 个三角形应用回交图片，区间 ${m.interval[0]}–${m.interval[1]} 秒（含起点、不含终点）。保留原网格、权重与动作；换图不会修复投影方向错误、网格翻转或压缩。请检查切换瞬间与整体轮廓，仍需阶段验收。`;
      section.append(p);
    }
    if(report.boundary){const p=document.createElement('p'),b=report.boundary;
      p.textContent=`分区边界检查：${b.status}；${b.failed_times}/${b.sample_count} 个采样时刻超限，最大分离 ${b.worst?b.worst.gap_px.toFixed(3):'0'} px（门槛 ${b.limit_px} px）。这是边界顶点检查，尚不代表纹理接缝或视觉通过。`;
      section.append(p);
      if(b.worst){const locate=document.createElement('a');locate.textContent=`查看边界 ${b.worst.time.toFixed(3)} 秒`;
        locate.href=`/api/motions/${encodeURIComponent(job.job_id)}/view/player.html?time=${b.worst.time}`;section.append(locate);}
    }
  }catch(error){section.textContent='无法读取修正对照：'+error.message;}
}
