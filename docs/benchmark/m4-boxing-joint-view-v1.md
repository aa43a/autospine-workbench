# Boxing: joint limb and torso view qualification

2026-09-28. This is source-sampled qualification, not visual acceptance or a new Runtime capture.

## Evidence

- Source job: `motion-0239e8622d68464bad355b4527c878f3`, boxing, 67 samples.
- Verified source bundle: `140fabcf63c9f47995ce9fe291aeb848522179f90df27ca96e341f331d232cad`.
- Comparison: `E:/proj/unusual/localset/tmp/m4-boxing-source-v1/joint-view-comparison.json`.
- Independent Hongmeiling −75° experiment: `E:/proj/unusual/localset/tmp/m4-boxing-hongmeiling-view-v1/report.json`.
- Experiment artifact: `b36d4bfb7b9448d541882bb259b3f4c3e64c258ccd6da42885da0894b9900871`.

The fixed −75° experiment removes the original right-arm geometry failure but fails other geometry and torso checks. Its moving-ankle check passes at 641 samples, maximum error about 0.0441 px; that does not certify sole contact. It has no new official Runtime capture and is not adopted.

## Change

Automatic oblique comparison now qualifies limb projection together with the reference torso plane. The reference assumption is explicitly the initial source at zero additional yaw matching front artwork. Torso width, height, shear, side degeneracy and back-facing checks use the existing torso policy thresholds. No threshold was relaxed.

Each angle retains separate limb/torso results, failed torso times and reasons. An angle which improves limb visibility cannot be recommended when the torso turns behind the available artwork. Degenerate torso data produces an unqualified angle, not a server failure. Comparison profile moves to v2, so stale suggestion hashes must be recomputed at submission. Existing candidate identities and human reviews are unchanged.

For this boxing clip, all 13 angles from −90° through +90° fail joint qualification. Zero yaw passes torso checks but fails limb checks; −75° fails torso checks at 15 source samples, including back-facing samples. This does not establish that every continuous or time-varying camera is impossible. It establishes that this supported fixed-angle grid cannot resolve the clip using the current projection constraints.

## Validation and remaining work

15 Python tests pass (comparison, actual torso geometry, and HTTP intake route); the pose-selection JavaScript test also passes. Regression coverage explicitly rejects a back-facing torso when limb checks pass, retains its failing time, and preserves stale-selection rejection.

The existing workbench auto-angle endpoint and UI use this logic after service reload. Production service was not restarted in this slice; no live browser claim is made. No new boxing visual acceptance is requested. Further boxing work needs a depth-aware local limb representation or appropriate alternate artwork, followed by target geometry, contact, occlusion and Runtime verification. M4 remains active.
