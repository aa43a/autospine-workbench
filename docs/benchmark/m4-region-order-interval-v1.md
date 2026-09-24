# Region order intervals

The order-only compiler now supports an explicit animation and half-open time
interval. It keeps the partition's original setup order, moves the selected runs
at the start, and restores setup order at the end. Other animations are unchanged.
The static operation remains compatible. Existing draw-order tracks remain rejected
rather than silently overwritten.

This is an explicit candidate edit, not automatic depth inference or visual approval.
It does not alter bone weights, UVs, deformation tracks, or animation duration.
Depth QA sampling includes both sides of each draw-order boundary.

## Verification

- Nine Python tests passed across interval order, static order, and compaction.
- Reused the actual Alice source scene and 19-triangle selection from
  `tmp/region-order-live-v1`, with a test interval of 1 to 2 seconds. That interval
  is a technical probe, not an accepted semantic crossing interval.
- Official Spine core 4.3.13 checked 14 boundary, reverse-seek, and loop samples.
- Official core compared 478 frames / 730,384 vertex positions against the source:
  exact Float32 equality after compact vertex remapping.
- Target remains Spine 4.3.26; the tested runtime version is recorded separately.

Tools: `check-region-order-interval.mjs` and `check-region-order-core.mjs`.
Local evidence: `tmp/region-order-live-v1/interval-check.json` and
`interval-identity.json`.

## Remaining work

The interval is now exposed through the workbench editor, draft history, immutable
queue requests, worker dispatch, candidate bundle and summary. Static drafts remain
compatible. Invalid, empty and out-of-duration intervals are rejected.
52 focused Python tests and JavaScript syntax checks passed. Live browser testing
on the Alice parent motion-d556e3bdce29417db09a94cbac9fc0da restored the existing
19 triangles, saved a 1–2 second interval as revision 2, and reloaded it correctly
with no page errors. This is an engineering probe, not visual acceptance.
The service restart preserved all 164 historical job states.

Next capture the switch frames for visual review and select intervals from real
crossing evidence. Correct order and unchanged geometry do not prove a natural material seam.
Reach and Squat across the original three characters remain unfinished.

## Live queue result and capture follow-up

Job `motion-744b6a402ba546c783b50cc871a653d5` completed successfully, producing
artifact `24a39f6e66829e2595bb90c1461d755f531be1c45df0cf1a1cb83b37ae007b23`.
Official core/WebGL 4.3.13 captured 2,106 reference frames and checked draw order
against the JSON offsets. The real output switches at 1 second and resets at 2.
The downloaded 117-file ZIP matched its manifest hashes, and its skeleton matched
the scene served to the player. Thirteen regional geometry records still fail;
the result remains needs_changes, with no visual acceptance.

The capture tool now explicitly saves existing reference frames immediately before
and at/after draw-order switches, plus the following frame. Its report records the
authored time, Float32 runtime key time, exact-sample availability, and offsets of
the selected samples. It does not claim to capture an exact switch if the reference
grid does not contain it. This closes a screenshot-selection gap in the default
32-frame stride. `node tools/check-character-order-probes.mjs` passed, including
non-exact keys, endpoint switches, out-of-grid keys, and invalid frame order.
This new selector was added after the live job started; that immutable report does
not contain the new switch screenshot coverage. Fresh capture is still required.

## Boundary inspection and precision

The actual official player was inspected at 0.999, 1.000, 1.999 and 2.000 seconds.
At the full-character display scale no obvious new jump was visible. This does not
prove pixel continuity or improvement: the selected waving example does not establish
that the order edit repairs the original Reach shoulder. Do not count it toward
the original six-case quality acceptance or automatically adopt the interval.

A separate precision defect was reproduced: authored endpoints 0.5 and 0.500000001
both become 0.5 in Runtime Float32 storage. Such collapsed intervals are now rejected.
Reports preserve authored endpoints and record effective runtime endpoints; supplemental
depth probes use runtime key times. Official core verification of the real Alice
scene with 0.1–0.3 endpoints passed 14 boundary/reverse/loop checks. Thirty-three focused
Python tests passed. This is timing correctness, not visual acceptance.
