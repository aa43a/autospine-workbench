# Same-source target view regression

`tools/m4_view_comparison_report.py` joins variants only when character artifacts,
raw motion bytes, baseline digest and execution profiles match. Completed target
projection parameters must match the plan. All original baseline combinations
remain visible; missing variant cases and unfinished evidence never count as passes.
The report links each exact player, contact and depth inspection page.

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
