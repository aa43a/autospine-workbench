export const kneeLabels={projected_bend_reversed:'可见弯曲方向反转',target_bend_flattened:'目标弯曲投影接近拉直',
  source_bend_hidden_in_depth:'源弯曲主要藏在深度方向',source_nearly_straight:'源接近伸直',
  unobservable:'无法观测',projected_side_consistent:'可见弯曲方向一致'};

export function kneeRows(report,artifact){
  if(report.artifact_sha256!==artifact)throw Error('候选身份变化');
  if(report.profile!=='knee-projection-observation-v1'||!Array.isArray(report.rows)||!report.rows.length)
    throw Error('膝部采样证据不完整');
  const previous={};const rows=report.rows.map(row=>{
    if(!['left','right'].includes(row.side)||!Object.hasOwn(kneeLabels,row.status)||!Number.isFinite(row.time)||row.time<0||
      (previous[row.side]!==undefined&&row.time<=previous[row.side]))throw Error('膝部采样证据不完整');
    previous[row.side]=row.time;const source=row.source;
    if(!source||!['measured','folded_chord_unobservable'].includes(source.status))throw Error('膝部采样证据不完整');
    if(source.status==='measured'&&(!Number.isFinite(source.bend_degrees)||source.bend_degrees<0||source.bend_degrees>180||
      !Array.isArray(source.projection_visibility)||source.projection_visibility.length!==2||
      source.projection_visibility.some(v=>!Number.isFinite(v)||v<0||v>1+1e-9)||
      (source.screen_plane_alignment!=null&&(!Number.isFinite(source.screen_plane_alignment)||source.screen_plane_alignment<0||source.screen_plane_alignment>1+1e-9))))
      throw Error('膝部采样证据不完整');
    const visibility=source.status==='measured'?Math.min(...source.projection_visibility):null;
    const issues=[];
    if(['projected_bend_reversed','target_bend_flattened','unobservable'].includes(row.status))issues.push(kneeLabels[row.status]);
    if(row.status==='source_bend_hidden_in_depth')issues.push('需要同时对照源侧视，不能仅凭屏幕方向判断前弯或后弯');
    if(visibility!==null&&visibility<.5)issues.push('骨段投影长度低于原长一半：重点检查膝部轮廓与姿态表达');
    return {...row,visibility,issues};
  });
  if(!['left','right'].every(side=>rows.some(r=>r.side===side)))throw Error('膝部左右采样缺失');
  const left=rows.filter(r=>r.side==='left').map(r=>r.time),right=rows.filter(r=>r.side==='right').map(r=>r.time);
  if(left.length!==right.length||left.some((t,i)=>t!==right[i]))throw Error('膝部左右时间不一致');
  return rows;
}

export function strongestKnee(rows){
  return rows.reduce((best,r,i)=>r.issues.length&&(!rows[best].issues.length||(r.visibility??0)<(rows[best].visibility??0))?i:best,0);
}
