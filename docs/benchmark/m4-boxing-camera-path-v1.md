# Boxing continuous-camera feasibility

2026-09-28. M4 remains active. This experiment does not modify or approve a character candidate.

## Deployment verified

The authorized 8918 workbench service was restarted only after checking its process identity and confirming no pending/running motion jobs. The new process is 27372. The real boxing source `motion-0239e8622d68464bad355b4527c878f3` now returns `whole-source-oblique-selection-v2` from `/compare-oblique`, with no recommended angle. Comparison SHA: `13a83d71ac70a0eeae959c8a4d82e358813b385b30aa75d681064a666e77e6eb`.

This is HTTP verification; no browser interaction is claimed.

## Experiment

`camera_path.plan` searches a single shared camera for all limbs and the torso. It starts at zero additional yaw, uses a one-degree grid in [−90°,90°], and retains the existing source visibility, relative-length and reference-torso gates. A dynamic-programming path enforces a finite camera speed and favors small camera rotations. It does not use different cameras for different body parts. Failed searches retain their first unreachable frame, preceding reachable angles and current qualified angles.

The immutable diagnostic is `E:/proj/unusual/localset/tmp/m4-boxing-source-v1/camera-path.json`. Reproduction:

```powershell
$env:PYTHONPATH='src;tools'
python tools/m4_camera_path_probe.py workspace workspace/jobs/motion-intake-v1/motion-6c01b6ac334947729089deabcb1dbed5/request.json NEW_OUTPUT.json
```

On the verified 67-frame boxing source:

| Experimental speed limit | First unreachable time | Minimum next-frame turn from reachable set |
|---|---:|---:|
| 60°/s | 0.400000 s | 7°, requiring approximately 210°/s |
| 90°/s | 0.666667 s | 49°, requiring approximately 1470°/s |

Each individual source frame has some qualified angle, but those angles do not form a path under these speed bounds and this grid. This is not a proof against all continuous projections, other start views, or alternate artwork. A feasible source path would still require interpolation, angular-acceleration, character geometry, contact, depth, Runtime and visual checks.

## Validation and next action

Three new tests cover a feasible bounded path using actual torso geometry, disconnected qualified frames, invalid/unobservable input, and preservation of source data. The experiment never changes adoption authority or existing human decisions.

Global camera search is insufficient for this clip under the current bounded strategy. The next adaptation work should address the near-camera forearm representation and its local depth/occlusion, with a separate candidate and full target validation. Do not silently clamp projected limb length or claim that a camera jump is a visual repair.
