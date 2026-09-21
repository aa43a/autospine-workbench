// Consecutive source samples form an interval, not many duplicate warnings.
export function rotationEvents(row, labels){
  const result=[];
  for(const event of row.source_events){
    const previous=result.at(-1);
    if(event.reason==='projection_direction_unreliable'&&previous?.reason===event.reason
        &&Number.isInteger(event.frame)&&event.frame===previous.lastFrame+1
        &&event.time>previous.end){
      previous.end=event.time;previous.lastFrame=event.frame;previous.samples++;
    }else result.push({reason:event.reason,time:event.time,end:event.time,
      lastFrame:event.frame,samples:1,text:labels[event.reason]||event.reason});
  }
  for(const event of row.large_key_intervals)result.push({time:event.start_time,end:event.end_time,
    text:`局部关键帧转动 ${event.delta_deg.toFixed(1)}°；源传递 ${event.source_delta_deg.toFixed(1)}°`});
  if(row.maximum_transfer_difference_deg>1e-6)result.push({time:row.maximum_difference_time,
    end:row.maximum_difference_time,text:'最大传递差异；接触修正也可能有意改变局部角度'});
  return result.sort((a,b)=>a.time-b.time);
}
