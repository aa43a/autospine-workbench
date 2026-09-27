# Preserve near-camera uncertainty in the candidate issue list

2026-09-28. Absolute source-pose fitting records low-visibility source frames in `source_pose_fit.records[].unreliable_frames`. The detailed readiness view already reads these records. Previously the worker's top-level `issues` and candidate status did not necessarily reflect them, so consumers reading only the candidate summary could miss this projection limitation.

New candidates now include `motion_source_pose_direction_unreliable` as a projection issue whenever a fitted record has unreliable frames. The original per-bone/frame evidence remains unchanged. The candidate retains `needs_changes`; a numeric geometry pass cannot erase source-direction uncertainty. The workbench provides a Chinese explanation for this issue.

This is prospective behavior: existing immutable bundles, saved decisions and evidence hashes are not rewritten. The Hongmeiling front-pose boxing build started before this patch; its existing detailed readiness check remains authoritative, and its artifact must not be described as produced by the new issue propagation.

Validation: 17 tests across target pose, target intake and source fitting passed, including a candidate-level test that checks the stored issue, status and original frame evidence. Frontend syntax check passes; `motion-center.js` remains 365 lines.

The front-pose experiment continues in `E:/proj/unusual/localset/tmp/m4-boxing-front-pose-v1/`. At this record's creation it has reached depth-overlap checking; no new candidate pass, Runtime result or acceptance is claimed here.
