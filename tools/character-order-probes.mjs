// Preserve frames around every order switch; do not invent unsampled evidence.
export function orderProbes(document, reference) {
  const result = {};
  for (const [animation, frames] of Object.entries(reference.animations)) {
    const keys = document.animations[animation]?.drawOrder ?? [];
    if (!keys.length) continue;
    if (frames.some((f,i)=>!Number.isFinite(f.time)||f.time<0||(i&&f.time<=frames[i-1].time)))
      throw Error('order_probe_frame_times');
    result[animation] = keys.map(key => {
      const authored = key.time ?? 0, time = Math.fround(authored);
      if (!Number.isFinite(time)||time<0) throw Error('order_probe_key_time');
      const after = frames.findIndex(f=>f.time>=time);
      const before = after<0?frames.length-1:after-1;
      const indices = [...new Set([before,after,after<0?-1:after+1].filter(i=>i>=0&&i<frames.length))];
      return {authored_time:authored,runtime_time:time,
        before_available:before>=0,after_available:after>=0,
        exact_sample:after>=0&&frames[after].time===time,
        samples:indices.map(index=>({index,time:frames[index].time,offset_seconds:frames[index].time-time}))};
    });
  }
  return result;
}
