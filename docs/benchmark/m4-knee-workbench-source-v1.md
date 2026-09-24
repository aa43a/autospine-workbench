# Same-source knee diagnosis in ordinary motion jobs

The ordinary motion card now exposes the existing knee direction/depth panel and
seeks the same inline player/source comparison. Previously this panel was reachable
from cohort/experiment views only. No source motion, candidate, or acceptance changed.

The backend verifies character and source bundle identities and reconstructs the
declared view and clip before matching the stored MotionIR. Clipped diagnostics
now use player-local time and retain original source time. An explicit null
projection works; multiple animation names or mismatched view/source are rejected.
Experimental candidates whose manifest/actual MotionIR do not match their parent
request must provide the correct provenance rather than receive a misleading report.

20 Python tests passed across knee source mapping, knee geometry and rotation
diagnostics, including inherited fixture tests. JavaScript syntax check passed.
Service restart preserved 165 terminal jobs.

## Actual squat candidates

Each returned 114 leg observations (57 source frames × two legs):

| Character / job | Source bend hidden in depth | Projected side consistent | Flattened target |
| --- | ---: | ---: | ---: |
| Huiye / motion-b5610841e66e4f599d58360ef9de20bb | 13 | 100 | 1 |
| Hongmeiling / motion-e2f8058160c14d959d468d75cc53a35e | 13 | 98 | 3 |
| Alice / motion-8a48f34642c643e397f95b433046b8bb | 13 | 100 | 1 |

These are existing post-contact candidates, not a newly captured or newly accepted
three-character regression. Their immutable artifacts are respectively d8024a97a0837e56f5e19813df3daf4fdfcaa0d62591a2c45446865e2b634c48,
b682ae45d064f3106f6af72ab23d5c3c5170d3b0d1c0d39773091fd61c761dc9,
and 2424c43da460100d70b0c4d43ef380da86b999fd8daa8beba04e98480005479c.

Live browser testing opened Hongmeiling's panel and sought its inline player.
At 1.033 seconds it reports 129.3 degrees of 3D bending, 35.4% upper-leg projected
length and 74.3% lower-leg projected length. Bone-side consistency does not prove
a correct texture contour. The existing geometry failures remain. No page script
errors were observed. This supports continuing material/contour diagnosis rather
than blindly reversing the screen-space knee.
