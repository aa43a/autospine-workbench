# Wrist-anchored sleeve depth candidate

The existing segment-depth model cannot observe independent cloth helpers. A new
isolated experiment explicitly models a sleeve in the plane spanned by the source
forearm and screen vertical. The target elbow/wrist positions and normalized
source elbow/wrist depths define `z = a*x + c`, with no screen-vertical gradient.
This is a model assumption, not measured cloth depth, thickness or axial twist.

The caller must supply the helper and mapped forearm explicitly. The helper must
be parented to that forearm at its setup endpoint and remain coincident with the
hand root at the sampled time. Missing source depths or detached helpers abstain.
When the projected forearm's horizontal component is below 10% of its length,
the plane is ill-conditioned and unavailable; no nearest-bone fallback is used.
The cutoff is an experimental conditioning guard, not a validated visual range.

Run from the repository with `PYTHONPATH=src;tools`:

```powershell
python -X utf8 tools/m4_sleeve_depth_planes.py motion-883cb61bb3a84aee91f233cca536a552 ../tmp/m4-motion-center/sleeve-depth-plane-huiye-v1.json --helper cloth-layer-002-component-0000=forearm_r --helper cloth-layer-003-component-0000=forearm_l
```

Output creation is exclusive. Source/candidate identities, original rig/textures,
and character metadata are verified before sampling. The same observed-position
midpoint interpolation as regional Kimodo checks is used. BVH sources use the
existing bounded linear-channel sampler. Candidate packages are not modified.

The real Huiye wave report has SHA256
`07c2fba66f6654a091ea9e944c248f3cb403399e82e5cfaa678c9fadaa33b1f0`.
Right sleeve: 239/239 sampled planes available. Left sleeve: 229/239 available;
10 degenerate samples occur at 0.7833335–0.85 and 3.8–3.866667 seconds. These are
sample locations, not proven continuous unsupported intervals. Ten focused
plane/replay/weighted-interval tests pass, including mirroring, scale, attachment
invariants, missing observations and degenerate projection.

## Mixed influence experiment

`m4_regional_source_check.py` now accepts explicit repeated
`--sleeve-helper helper=forearm_l/r` arguments. The option is absent from default
workbench requests. It keeps ordinary arm influence intervals, evaluates helper
influence positions through the actual animated affine transform and deform, and
combines all contributions using the original weights. Unknown body influences,
unavailable helper planes and invalid normalization remain unknown. Unaffected
vertices retain their original intervals. Every applicable check records the
helper planes, unavailable reasons and vertices receiving model-derived depth.

The full Huiye run at
`../tmp/m4-motion-center/regional-kimodo-huiye-sleeve-plane-v1/report.json` has SHA256
`048e0e2f67ca214011f15880b16f20cb8007d58121661c00e76652f934eb6e0f`.
All 1,820 sample identities match the corrected source-scope baseline. Of those,
1,288 no-overlap checks stay unchanged, 490 remain uncertain, two become uniform
back under this model, 31 stay unmeasured, and **nine previously measured checks
hit the pixel budget**. Across 1,780 mutually measured checks, summed unknown pixel
contributions decrease from 6,196,801 to 709,073 (repeated pixel/sample counts,
not unique pixels, a correctness metric or an error rate). Of the remaining 490
uncertain checks, 452 still contain unknown depth and 38 have margin uncertainty.

This candidate is not adopted: 40 checks are unmeasured and 120 first-blocker
ordering records remain. No transformed skeleton or Runtime capture is produced.
Twenty-six focused tests pass, including mixed/all-helper/all-body weights, actual
helper-space deform, unknown preservation and default-off parameter propagation.
Further work must resolve remaining unknown influence sources and the resource
regression before this can enter default selection. Model-derived depth is not
observed cloth surface or human visual approval.
