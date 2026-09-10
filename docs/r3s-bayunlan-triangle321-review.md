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
