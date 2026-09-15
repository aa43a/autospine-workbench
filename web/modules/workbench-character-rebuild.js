"use strict";

// Only the new backend can revalidate residual scope after a motion rebuild.
export function canRebuildCharacterMotion(overview){
  return overview?.motion_rebuild_with_region_revalidation===true
    &&overview?.final_region_exclusions?.active===true
    &&!["order_review","post_component_regions","component_mounts"].some(key=>overview?.[key]?.active);
}
