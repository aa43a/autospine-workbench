"use strict";
const REQUIRED=['idle','wave-left','walk'];

// Select preview inputs only. This does not approve bindings or visual output.
export function defaultCharacterMotion(choices){
 const complete=(choices||[]).filter(row=>row.available===true&&typeof row.choice_id==='string'
  &&/^[a-f0-9]{64}$/.test(row.choice_id)&&Array.isArray(row.animations)
  &&REQUIRED.every(name=>row.animations.includes(name)));
 return complete.length===1?complete[0].choice_id:'';
}
