# Reach contact and source tracking comparison

2026-09-27. Diagnostic separation only; existing contact gates are unchanged.

Hongmeiling side-view raised-arm candidate `motion-c22f2a09ce804829ab7cc9a4ecf0ebbd`
has an exact-current revision 1 human stage decision, `accepted_with_exceptions`.
The user accepted this specific candidate while retaining known limitations. This
does not replace the fixed baseline or accept other motions.

Reach candidate `motion-1fa64acfd3c046f5a296ac80ddd8b925` uses the same source and
character as `motion-b05c1504631641cf93bf1f718bdbaa6d`, with the moving-source-ankle
profile and stationary correction disabled. Artifact:
`0676e36dcc32face75e1811e01d3193b31a7118e57dd813bd6c0a039202ccf7a`.

- 737 official Runtime geometry samples passed, zero failed records.
- Final moving-ankle error: 0.0007330765 px, below the 5.4937006131 px threshold.
- At the contact samples, left source/target displacement both round to 0.866 px;
  right source/target displacement both round to 5.619 px.
- Right stationary displacement remains above the threshold. Contact status is
  `inferred_proxy_drift`; this candidate is not adopted or visually accepted.
- The parent source qualification already classified the right interval as
  nonstationary (3D drift/reference 0.01027769), unlike the left (0.00162343).

The contact page now displays projected source displacement, target displacement,
and same-time tracking error separately. It interpolates source targets at the
actual contact samples, anchors each interval at its own start, and requires both
final checks to match the current skeleton. It never changes the evidence or
converts source motion into proof of floor contact. This isolates support-label
uncertainty from retargeting error; do not widen thresholds to erase the warning.

18 focused Python tests passed. The real candidate was rendered to
`E:/proj/unusual/localset/tmp/m4-reach-contact-comparison-v1.html`, with timeline
links to the exact workbench candidate.

Deployment follow-up: all 174 motion jobs were terminal before the authorized
8918 service reload. The exact candidate's online `view/contact.html` returned
HTTP 200 with the comparison heading and 0.000733 px tracking error. Browser
connection still returned `nodeRepl.fetch request failed`; browser interaction
has not been independently tested. No gate or stored acceptance changed.
