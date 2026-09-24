// Reuse exact float32 boundary selection for each independent attachment track.
import {orderProbes} from './character-order-probes.mjs';
export function attachmentProbes(document, reference) {
  const result = {};
  for (const [animation, frames] of Object.entries(reference.animations)) {
    for (const [slot, channels] of Object.entries(document.animations[animation]?.slots ?? {})) {
      const keys = channels.attachment ?? [];
      if (!keys.length) continue;
      const selected = orderProbes({animations:{[animation]:{drawOrder:keys}}}, {animations:{[animation]:frames}})[animation];
      (result[animation] ??= []).push(...selected.map((row,index)=>({...row,slot,attachment:keys[index].name??null})));
    }
  }
  return result;
}
