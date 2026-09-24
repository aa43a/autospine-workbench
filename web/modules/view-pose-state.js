// Authored control state only. Interpolation is a preview, never a saved observation.
export function createViewState(template) {
  const value=structuredClone(template), controls=value.control_template;
  if(!controls?.source_uv?.length||!controls.target_xy?.length)throw Error('模板缺少控制网格');
  let points=structuredClone(controls.target_xy), selected=0;
  const poses=value.view_pose.poses;
  return {
    value, controls, get points(){return points;}, get selected(){return selected;},
    select(index){selected=index;},
    move(mode,index,point){
      if(!Number.isInteger(index)||index<0||index>=points.length||!point.every(Number.isFinite))throw Error('控制点无效');
      if(mode==='uv') {
        if(point.some(v=>v<0||v>1))throw Error('UV 必须位于图片内');
        controls.target_uv[index]=[...point];
        for(const pose of poses)pose.correspondence.target_uv=structuredClone(controls.target_uv);
      } else points[index]=[...point];
    },
    save(time,start,end){
      const duration=template.view_pose.interval[1];
      if(![time,start,end].every(Number.isFinite)||!(0<=start&&start<time&&time<end&&end<=duration))throw Error('姿态时间必须严格位于生效区间内');
      if(poses.some(p=>p.time!==time&&(p.time<=start||p.time>=end)))throw Error('已有姿态超出新区间，请先删除或调整');
      const pose={time,correspondence:{...structuredClone(controls),target_xy:structuredClone(points)}};
      const index=poses.findIndex(p=>p.time===time);
      if(index<0)poses.push(pose);else poses[index]=pose;
      poses.sort((a,b)=>a.time-b.time);value.view_pose.interval=[start,end];
    },
    remove(time){const index=poses.findIndex(p=>p.time===time);if(index>=0)poses.splice(index,1);},
    sample(time){
      if(!poses.length)return;
      let a=poses[0],b=poses.at(-1);
      if(time<=a.time)b=a;
      else if(time>=b.time)a=b;
      else for(let i=1;i<poses.length;i++)if(poses[i].time>=time){a=poses[i-1];b=poses[i];break;}
      const t=a===b?0:(time-a.time)/(b.time-a.time);
      points=a.correspondence.target_xy.map((p,i)=>p.map((v,k)=>v+(b.correspondence.target_xy[i][k]-v)*t));
    },
    export(){if(!poses.length)throw Error('请先保存至少一个姿态');return structuredClone(value);}
  };
}
