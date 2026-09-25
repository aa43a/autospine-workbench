import {createCohortSync} from './motion-cohort-sync.js';

// Each related frame retains its own artifact guard; one failure does not stop others.
export function createRelatedSync() {
  const controls=new Set();let time=0,end=null;
  return {
    attach(frame,artifact,status) {
      const sync=createCohortSync(status);controls.add(sync);
      if(end!==null)sync.seek(time,end);
      sync.attach(frame,artifact);
    },
    seek(value,duration) {
      time=value;end=duration;
      for(const sync of controls)sync.seek(value,duration);
    },
    clear() {for(const sync of controls)sync.clear();controls.clear();},
  };
}
