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

This experiment does not yet supply mixed mesh influence depths, reorder slots,
produce a transformed candidate, or capture Runtime frames. Next validation must
combine ordinary arm influence intervals with explicit helper-plane influence
depths, retaining unknowns through degenerate samples and checking the full
restored regional inventory. It must not replace unknown cloth depth merely to
make an ordering gate pass. Neither visual acceptance nor default adoption has
been granted by this model-conditioning result.
