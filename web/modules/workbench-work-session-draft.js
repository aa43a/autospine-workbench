const prefix='autospine:work-session-draft:v1:';
const stages=new Set(['source_preparation','joints','bindings','sleeves','visual_review','auto_audit','other']);
export function createSessionDrafts(storage){
 const key=project=>prefix+encodeURIComponent(project);
 function valid(d){
  const start=Date.parse(d?.started_at),end=Date.parse(d?.ended_at);
  return d&&typeof d.source==='string'&&d.source.length>0&&/^[a-f0-9]{32}$/.test(d.session_id)
   &&stages.has(d.stage)&&d.method==='operator_stopwatch_segment_v1'
   &&Number.isFinite(start)&&Number.isFinite(end)&&Number.isFinite(d.seconds)
   &&d.seconds>=0&&d.seconds<=86400&&Math.abs((end-start)/1000-d.seconds)<0.01;
 }
 return {
  read(project){try{const record=JSON.parse(storage?.getItem(key(project))||'null');return record?.project===project&&valid(record.draft)?record.draft:null;}catch{return null;}},
  write(project,draft){try{if(!storage)return false;if(draft){if(!valid(draft))return false;storage.setItem(key(project),JSON.stringify({project,draft}));}else storage.removeItem(key(project));return true;}catch{return false;}}
 };
}
