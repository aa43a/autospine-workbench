export function appendCandidateDownload(container,job){
  if(job.status!=='succeeded'||!/^motion-[a-f0-9]{32}$/.test(job.job_id)
      ||!/^[a-f0-9]{64}$/.test(job.result?.artifact_sha256))return;
  const paragraph=document.createElement('p');
  const link=document.createElement('a');link.textContent='下载此候选 Spine 包';
  link.href=`/api/motions/${job.job_id}/download`;paragraph.append(link);
  const note=document.createElement('span');
  note.textContent=' · 下载保留当前技术异常，不代表已验收或发布。';paragraph.append(note);
  container.append(paragraph);
}
