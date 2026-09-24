// Measure the existing player clock without replacing its RAF or rendering loop.
export async function playbackProbe(page) {
  return page.evaluate(async () => {
    const control=window.characterPlayerControl;
    const duration=window.characterPlayerState.duration;
    if (!(duration>0 && duration<=10)) throw Error('bounded_short_clip_required');
    if (document.hidden) throw Error('visible_document_required');
    document.getElementById('speed').value='1';
    document.getElementById('loop').checked=true;
    control.seek(0);
    document.getElementById('play').click();
    const observations=[];
    const start=performance.now(), warmup=duration*1000, end=warmup+duration*3000;
    while (performance.now()-start<end) {
      await new Promise(requestAnimationFrame);
      const now=performance.now(),state=window.characterPlayerState;
      if (document.hidden || !state.playing) throw Error('playback_interrupted');
      if (now-start>=warmup) observations.push({wall_ms:now,time:state.time});
      if (now-start>60000) throw Error('playback_timeout');
    }
    document.getElementById('play').click();
    if (window.characterPlayerState.playing) throw Error('pause_failed');
    const intervals=[],steps=[];let wraps=0;
    for (let i=1;i<observations.length;i++) {
      const elapsed=observations[i].wall_ms-observations[i-1].wall_ms;
      if (elapsed>=duration*1000) throw Error('ambiguous_missed_loop_count');
      intervals.push(elapsed);
      let delta=observations[i].time-observations[i-1].time;
      if (delta<0) {delta+=duration;wraps++;}
      steps.push(delta);
    }
    if (wraps<2 || intervals.length<10) throw Error('insufficient_continuous_playback');
    const sorted=[...intervals].sort((a,b)=>a-b);
    const elapsed=observations.at(-1).wall_ms-observations[0].wall_ms;
    const advanced=steps.reduce((a,b)=>a+b,0);
    const report={observations,samples:intervals.length,wraps,wall_ms:elapsed,animation_advanced_seconds:advanced,
      animation_to_wall_ratio:advanced/(elapsed/1000),
      median_frame_interval_ms:sorted[Math.floor(sorted.length*.5)],
      p95_frame_interval_ms:sorted[Math.ceil(sorted.length*.95)-1],
      max_frame_interval_ms:sorted.at(-1),intervals_over_33ms:intervals.filter(v=>v>33.333).length,
      repeated_animation_samples:steps.filter(v=>v===0).length,
      scope:'RAF_observation_intervals_and_player_clock_not_GPU_presentation_or_visual_acceptance'};
    control.seek(0);
    return report;
  });
}
