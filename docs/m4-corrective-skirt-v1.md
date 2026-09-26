# Corrective skirt-depth localization

2026-09-26. Alice Squat candidate
`418038c3621a71b2a56893f53862b0611ce1feb7e0b232f75e786d09ff29dcb2`
has a new selected-pose diagnostic, using the same source BVH and explicit
minus-55-degree source camera as its construction request. No draw order,
material, weight or acceptance was changed.

`tools/m4_corrective_skirt_audit.py` verifies the candidate relation and Runtime
identity, then reuses the existing native-alpha overlap and garment-envelope
probe. Nine times cover the start, squat and return; this is not full-motion QA.

## Findings

Of 18 leg/skirt comparisons, six left-leg comparisons support the leg behind the
modelled skirt surface. Twelve comparisons retain ambiguous or unknown depth:
all nine right-leg times, plus the left leg at about 0.70, 0.93 and 1.17 seconds.
No comparison supports moving the whole leg in front. This does not prove the
true garment surface: the envelope uses an explicit assumed cross-section.
It also does not measure the visible leg pixels outside the overlap region.

Therefore the report does not authorize a global order change and does not
declare the exposed leg contour fixed. Actual source material, projection and
occlusion remain separate causes to inspect.

## Workbench result

The related-candidate UI now lists the selected times and leg/skirt pairs, with
buttons to load the exact pose in its candidate player. A diagnostic seek uses an
independent timeline so source-playback synchronization cannot immediately move
it away. Replaced synchronized frames detach their listeners.

Registration `e27cc25bebce244021fba5111b13c95ce5d4dd3a9b4c4c79327a4eba5f979f04`
retains the existing foot-proxy checks and adds these skirt diagnostics. The live
report endpoint returned nine poses, 18 rows, `requires_review`,
`order_changed=false`, and `selected=false`. Prior registrations remain intact.
The same receipt is included in candidate downloads.

Twenty Python tests pass, plus the pure-JavaScript diagnostic-label and exact-time
callback check. Live browser interaction remains unverified because browser
permissions are unavailable. An older standalone synchronization script failed
at import because its external browser dependency was unset; it did not launch a
browser and was not retried as an alternative to the supported browser tool.
