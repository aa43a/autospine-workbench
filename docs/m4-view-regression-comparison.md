# Same-source target view regression

`tools/m4_view_comparison_report.py` joins variants only when character artifacts,
raw motion bytes, baseline digest and execution profiles match. Completed target
projection parameters must match the plan. All original baseline combinations
remain visible; missing variant cases and unfinished evidence never count as passes.
The report links each exact player, contact and depth inspection page.

## Workbench comparison

Completed character-motion cards expose **比较该角色的已有视角候选**.
GET `/api/motions/{target_job}/compare-targets` groups existing requests by exact
source byte identity and format, character artifact/job/project, clip, contact
option and execution profiles. Different views are compared; different sources,
rig revisions, crop ranges or policies are not mixed. Each succeeded candidate is
revalidated against current source/character state, verified artifacts, Runtime
evidence and its stage-review history. Outdated tasks remain visible.

Only `stage_review` technical readiness qualifies for a recommendation. Human
rejection and changed review evidence exclude a candidate. An exact existing
`accepted` decision is preferred among qualified candidates; other ties use job
identity for reproducibility, not an aesthetic score. No review or artifact is
changed. More than 24 matching candidates declines recommendation rather than
ranking a silently truncated sample. This compares already built candidates; it
does not yet construct all camera angles for each new character.

Actual check: `motion-6d7be7b37ac141c1906cf28ca5eb4c74` groups four Hongmeiling
raise-arms targets and recommends the side candidate
`motion-c22f2a09ce804829ab7cc9a4ecf0ebbd`. The front and both -30 degree candidates
retain exceptions. The automatic and manual -30 builds remain separate records.

Validation: exact grouping, changed source/rig/clip/policy exclusion, outdated
inventory, rejection/evidence-change exclusion and bounded recommendation tests.
`tools/check-motion-target-comparison.mjs JOB_ID` performs a read-only browser
check against the live workbench and its actual candidate evidence.

## Depth failure localization

The existing `depth-ownership.html` entry now handles both draw-order cycles and
visible source-depth straddles, choosing the earlier evidenced failure. This is
the versioned `first-depth-failure-ownership-v2` diagnostic; candidate animation,
QA thresholds and adoption remain unchanged. It displays the source depth range,
actual native-alpha overlap ownership and a link to the exact playback time.

On the automatic Hongmeiling -30-degree candidate, the first failure is at
0.166667 seconds: left-arm slot `layer-006` overlaps chest slot `layer-009` at
951 sampled pixels. Source relative depth ranges from -0.185193 to +0.031209.
Both attachments use recognized body weights, but that does not establish one
depth side for all overlap pixels. Whole-arm reordering is therefore still not
adopted. A later arm/skirt cycle at 1.4 seconds no longer hides this earlier issue.

Current completed runs:

| Matrix | Runtime captures | Geometry passes | Ready for stage review |
| --- | ---: | ---: | ---: |
| Front: 8 categories × 3 characters | 24 / 24, 11,334 frames | 11 / 24 | 0 |
| Side: 4 changed categories × 3 characters | 12 / 12, 6,978 frames | 11 / 12 | 1 |
| Oblique: the same 4 categories × 3 characters | 12 / 12, 6,531 frames | 10 / 12 | 0 |

These denominators differ, so the headline ratios are not a controlled comparison
of view quality. The row-aligned report provides the appropriate same-source pairs.
Five side candidates have only partially corrected support and retain exceptions.
No stage acceptance records were read into this snapshot. Runtime completion
alone is neither visual acceptance nor production authorization.

The side raise-arms Hongmeiling candidate
`motion-c22f2a09ce804829ab7cc9a4ecf0ebbd` is ready for stage review:
inferred support corrected, geometry passed, sampled draw-order candidate applied.
Human visual feedback has been requested and is pending.

The oblique cohort has completed. Walking passes geometry on all three characters
but retains support drift. Raise-arms passes geometry and current support checks
on all three, but retains depth exceptions. Squat has geometry failures on Alice
and Hongmeiling; Huiye passes geometry and support. Reach passes geometry on all
three with only partial support correction. Every oblique case retains depth
exceptions. The smallest source-qualified yaw is therefore not a demonstrated
best target view: the matched side cohort has one more geometry pass and one
stage-ready candidate. No gates were relaxed to select these results.

The generated comparison is a snapshot at
`../tmp/m4-motion-center/view-comparison-current.html`, not a live progress monitor.
Re-run the reporter with the three plan/state pairs to refresh it. Generic cohort
report headings now show actual source views and projection offsets rather than
incorrectly labeling every matrix as eight categories with front projection.
