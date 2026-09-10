# Bayunlan triangle 321 review

On 2026-09-10, after the diagnostic texture bounds were corrected, the user explicitly
confirmed left-sleeve triangle 321 as drape ("属于垂布"). Only `layer-004/component-0000`
triangle 321 changed from `unknown` to `hanging_cloth`, with origin `manual_edit`.
No other triangle, vertex, joint, binding or source texture was changed by this decision.

Prior draft: `a4e33f6e6c02507f31dadf8ec89390c47f9a9b46ccfe0bad4b9d8f2dd72c6d5a`.
Revised draft: `1443ed86c72b15a92514ccf4439f26a8d7ba973958b28e04c50724102051480b`.
The original download remains untouched. Previous and revised copies and the scoped
decision receipt are in `tmp/r3s-reviewed-321`; the normal workflow draft was updated.
The original 946-triangle inventory remains intact. Left drape count is now 252,
unknown count 5. The right-sleeve assignments are identical.

The ordinary workflow rebuilt all stages under
`tmp/r3s-reviewed-321-workflow/bayunlan/run-563e56b5b3278f923dbd0c30280726ae68319e45303a402230fc856646bf0c6f`.
It correctly reports `blocked`; stage execution success is not geometry or Runtime success.
Rebuilt cuff/envelope source: `318eadf943e53637f6be108d080c2c6d003de19947496b101d57da22497cb12e`.

New fixed-edge diagnosis: `bed71731374ff9d2bb8846e4fd2a08e0ed2fcc5a6278075c2463f582f1353114`.
The left fixed-edge peak falls from 3.124940118251171 to 1.604711447077818; no fixed-edge
counterexample remains among the recorded poses. This removes the previous necessary
constraint obstruction, but is not a proof that the complete deforming mesh passes.
Review: `tmp/r3s-reviewed-321-constraints/bayunlan/index.html`.

The regenerated left-sleeve failure counts for forearm/hand/cloth/pp/pm/mp/mm are
0/118/0/84/118/118/82. This is why the new ownership decision must feed a new correction
solve rather than directly receiving production or Runtime approval.

## Correction trial on the revised ownership

Candidate `7e8dd24525bd2d7460bc2b8e5cf080690807829eef182495d59da2b8dd1e4470`
uses the existing capped edge budget and neighbor seed, plus an opt-in finite corrective
line search (`--blend-backtrack`). When a full trial is rejected, offsets are blended
with the exact retained source at fractions 1/2, 1/4, 1/8. Each is independently replayed
at 129 samples and must pass the original nonregression, fixed-anchor and setup gates.
No threshold is relaxed. Old solver receipts are removed from blended tracks because
they no longer describe those keys; the chosen fraction and attempts remain explicit.

Right retained failure counts: 0/8/0/0/102/94/0. The mp improvement (96→94) comes from
the 1/8 backtrack, after the full trial was rejected. Left: 0/84/0/72/80/84/72.
All 14 retained gates, unchanged binding data, exact fallback on rejection, setup
poses and candidate authority were verified. Five backtrack/helper tests and three
source-quality tests passed. Both sleeves remain blocked; no new Runtime frames were
captured. Review: `tmp/r3s-reviewed-321-backtrack/bayunlan/index.html`.

## Fixed-area obstruction after the edge obstruction was removed

`777e492651078aec797001eaf512c6f714459170c6f207999ad1279d83748199`
adds an independent fixed-triangle area check to the same exact candidate and draft.
The protected vertices of left triangles 274 (`unknown`) and 276 (`cuff`) produce
minimum recorded area ratios 0.26304512914204314 and 0.09869252362715505. Both are below
the actual QA minimum 0.5, not merely the solver's tighter internal target 0.55.
All three vertices are protected, so changing neighboring free vertices cannot repair
these ratios. This does not authorize changing hand/unknown ownership or weights.
Right-sleeve protected triangles have no such counterexample (minimum 0.7292083995324811).

The report at `tmp/r3s-fixed-areas/bayunlan/index.html` includes purple failure overlays
and separate texture-aligned closeups for 274 and 276. Human classification of 274 was
requested; 321 remains the only newly confirmed assignment. No additional draft change
has been made. Five fixed-constraint tests and two image-coordinate tests pass, including
a counterexample where every edge length passes while the fixed triangle collapses.

## Subsequent scoped review: triangle 274

The user then explicitly classified left triangle 274 as drape ("垂布"). Only that
assignment was changed to `hanging_cloth/manual_edit`; triangle 276 stays `cuff`,
and the prior triangle 321 decision is retained. Revised draft:
`309b0157c0535860deba001add8a30651e419654d508aa881b949d0edbf9dc09`.
Prior draft, revised draft and decision receipt are in `tmp/r3s-reviewed-274`.
Validation confirms a single changed assignment and the unchanged 946-triangle inventory.
Remaining unknown triangles are right 255/418/420 and left 253/319/382/383.
These have not been implicitly reclassified. The normal one-click input now references
the new draft, and a fresh full workflow was started under `tmp/r3s-reviewed-274-workflow`.

That workflow completed with a correctly blocked result, run
`run-ea0963d0bbc92242054a2290e5af56986c86de2edca16cd5540b4c2e48752b09`.
Envelope `6b284a9b6078432a1fc1ad4075eb22a995b338def0a9e172671ee1c428d86eee`
has no protected-edge or protected-triangle counterexample. A separate 513-point check
per motion confirms zero fixed-triangle failures; minima are right 0.7292083995324811,
left 0.501103924883485. This is not a full free-mesh pass.

The correction trial `5ad19329cea8d1c2ade731019fd32be62156e07fe0bd3a5a006b5952eba0d78a`
improves several motions but retains a narrow left correction domain after stage fallback.
The new opt-in `--reviewed-domain` follows the exact artifact ancestry to the sealed draft,
validates skeleton and geometry, and reconstructs the existing garment connection domain.
It never uses an unrelated latest draft, and keeps hand/unknown vertices protected.
The attempted domain is recorded separately from retained mixed-track data.

Result `152c2e629ea8a664adf3d23f12291bfee584627d8f70912233a8c7d68dcd98cc`:
right failed counts 0/2/0/0/102/94/0; left 0/94/0/88/94/96/72.
All 14 retained gates and immutable bind data were verified; free/protected sets are
disjoint (32 protected vertices right, 35 left). Regressing trials remain rejected.
Two exact-source domain tests, three connection-domain tests and three quality tests pass.
Review: `tmp/r3s-reviewed-274-domain/bayunlan/index.html`. Both sleeves remain blocked.

## Subsequent right and left boundary confirmations

The user explicitly classified right 418/420, then left 382/383 as drape.
Scoped receipts are in `tmp/r3s-reviewed-right-boundary` and
`tmp/r3s-reviewed-left-boundary`; earlier 321/274 decisions and cuff 276 are preserved.
Latest draft: `e8be2af7c40f153e4b485f2ee6d8319cd3068409925362ab9141aae72406117b`.
All 946 assignments remain; only right 255 and left 253/319 remain unknown.

The full ordinary workflow completed under `tmp/r3s-reviewed-boundaries-workflow`,
run `run-c9b75513c68ec4413538e947ec0c43b6d2b40f4e8da72dcfe2e16384c3382a1b`.
Envelope: `63ccec31d648db6e544be91f9f2162e0c9b0a1a5d7e42e39d7acf6e26587aced`.
Failed samples in forearm/hand/cloth/pp/pm/mp/mm order:
right 0/0/0/0/38/38/0; left 0/21/0/1/29/29/5.
Both sleeves remain geometry-blocked; completed export/check stages do not imply
that blocked sleeves were exported or rendered by official Runtime.

The retained solver now permits an explicit finite 1–3 pass experiment (default 1).
Rejected intermediate keys can seed a later solve, but only a nonregressing improvement
can replace the retained track. No ownership, bind data, QA threshold or motion range
is relaxed. Tests cover rejected-seed isolation, early exit and the hard iteration bound.

Latest bounded correction result:
`2693b99fffc26f85080046889f3db66e750005b63dc00054cd774effc12d6956`.
Right retained failures: 0/0/0/0/29/29/0. Left: 0/0/0/0/0/0/0.
All 14 nonregression gates and unchanged bind fields were read back and verified.
This is an explicit solver experiment, not yet the ordinary workflow default.

Left passed all 1,799 Spine 4.3.26 target samples and official spine-core 4.3.13
samples (maximum error 0.000083571 px). Official spine-webgl 4.3.13 with ANGLE
SwiftShader captured 1,799 frames and 206,885 contact probes, zero failed probes.
Capture receipt: `3a815808364f3cbe51e0552422b4ba7ab30793cb5ff99a99ee0f5f87c0b33ff7`.
Capture/image/source hashes were checked by `review-sleeve-framebuffer.py`.
Review: `tmp/r3s-reviewed-boundaries-runtime/index.html`.
The overlap hook had no software-visible peak captures; this is not a complete
occlusion pass or human visual approval. Candidate authority remains none.

Right failures now involve four hanging-cloth triangles. Remaining unknown 255
has no adjacent failed triangle in the recorded diagnosis, and no fixed edge/area
counterexample was found. Do not request further ownership changes without new
evidence: the next work is local deformation analysis. Diagnostic receipt
`1b37a1cd5d671def0d1b311778c05232f0c919882b690a9c830b6413feb35a7f` is in
`tmp/r3s-reviewed-boundaries-constraints/bayunlan`.
