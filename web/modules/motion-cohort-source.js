// Verify the relationship, not just two independently valid job identifiers.
const near=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<=1e-6;
export function verifyCohortSource(source,job,link,{job_id,source_sha256},artifact) {
  if(source?.job_id!==job_id||source.status!=='succeeded'||source.source_sha256!==source_sha256
      ||job?.kind!=='adapt'||job.status!=='succeeded'||job.result?.artifact_sha256!==artifact
      ||link?.authority!=='none'||link.target_job_id!==job.job_id||link.artifact_sha256!==artifact
      ||link.source_job_id!==job_id||link.source_sha256!==source_sha256)
    throw Error('候选与当前源动作不匹配，请重新生成复核清单');
  const actual=source.result?.motion, recorded=link.motion_identity;
  if(!actual||!recorded||Object.keys(actual).length!==Object.keys(recorded).length
      ||Object.entries(actual).some(([k,v])=>recorded[k]!==v))
    throw Error('候选的动作编译版本与当前来源不同');
  const info=source.result, start=link.source_start,end=link.source_end;
  if(!near(link.source_fps,info.fps)||link.source_frame_count!==info.frame_count
      ||!Number.isInteger(info.frame_count)||info.frame_count<2||info.fps<=0
      ||!near(link.source_duration,info.duration_seconds)
      ||!near(info.duration_seconds,(info.frame_count-1)/info.fps)
      ||!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start
      ||end>info.duration_seconds+1e-6||!near(link.duration,end-start))
    throw Error('源动作与候选时间范围不匹配');
  const clip=link.clip, expected=job.result.clip??null;
  if(clip===null) {
    if(expected!==null||!near(start,0)||!near(end,info.duration_seconds))throw Error('源片段范围不匹配');
  } else if(!clip||!expected||!Number.isInteger(clip.start_frame)||!Number.isInteger(clip.end_frame)
      ||clip.start_frame<0||clip.end_frame<=clip.start_frame||clip.end_frame>=info.frame_count
      ||clip.start_frame!==expected.start_frame||clip.end_frame!==expected.end_frame
      ||!near(start,clip.start_frame/info.fps)||!near(end,clip.end_frame/info.fps))throw Error('源片段范围不匹配');
  return {start,end,duration:link.duration,clip,fps:info.fps,frameCount:info.frame_count};
}

export function sameSourceRange(a,b) {
  return Boolean(a&&b&&near(a.start,b.start)&&near(a.end,b.end)
    &&near(a.fps,b.fps)&&Number.isInteger(a.frameCount)&&a.frameCount===b.frameCount);
}
