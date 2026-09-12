# Same-source residual mesh support

The exact Huiye and Xiaoemo whole-character candidates still contain six low-alpha residual regions. Their 1,992 nontransparent pixels all have alpha below 8. Low alpha alone is not an exclusion decision.

`inspect-character-residual-support.py` maps each residual pixel center through its setup quad into the character coordinate system, then tests only weighted meshes belonging to the same manifest source layer. Animation channels are removed for this setup test. Offsets and bone rotations therefore cannot be mistaken for texture misalignment. Multiple mesh owners remain ambiguous; unsupported quad UVs fail explicitly.

| Character / region | Unique same-source mesh support | Outside meshes |
| --- | ---: | ---: |
| Huiye footwear residual | 5 | 53 |
| Huiye right sleeve residual | 651 | 1 |
| Huiye left sleeve residual | 396 | 0 |
| Xiaoemo footwear residual | 113 | 38 |
| Xiaoemo right sleeve residual | 448 | 4 |
| Xiaoemo left sleeve residual | 283 | 0 |

Total: 1,896 uniquely supported centers, 96 outside, zero ambiguous centers. The JSON reports record exact bundle, skeleton, manifest and texture identities plus every pixel result.

This supports a next **texture transfer candidate**, not deletion, binding acceptance or a claim of complete pixel coverage. Before moving pixels, check the full pixel footprint, target UV mapping, existing target alpha/color collisions and exact setup compositing. Preserve unsupported pixels as residual. Then rebuild atlas/texture evidence and validate the same animations in the official Runtime. No source asset, binding decision or workbench registration changed in this diagnostic.

Tests cover translated/rotated source coordinates, independence from animation at time zero, ambiguous overlapping owners and unsupported UVs. The geometry is sampled at pixel centers only; it does not prove filtering or dynamic seam safety.
