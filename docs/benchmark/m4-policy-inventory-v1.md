# Independent processing-policy inventory

The support report now includes a separate policy-variant family. The existing
strict view comparison is unchanged: it still requires the same processing
policies, character snapshot, source bytes, source sampling and clip.

`GET /api/motions/{job}/policy-variants` lists adapt jobs sharing the exact
source format/bytes/sampling, project, character job/snapshot and clip, but using
different contact, pose, ankle, torso, depth or Runtime-reference policies.
Each row identifies changed policies and its own verified artifact/evidence.
At most 24 rows are evaluated; larger inventories explicitly remain incomplete.
No technical recommendation, replacement, adoption or visual acceptance occurs.

The browser support-report collector reads these rows and independently checks
source relationships and current stage review. Policy variants have their own
cards, timeline links and exception entries. Their acceptance does not affect
fixed-baseline totals. Failed lookups remain missing evidence, including when
reading an older report without this new inventory.

Real Hongmeiling Reach baseline `motion-aa45429b532747c5954389a5c1a706c1` has three
policy variants, including newly accepted `motion-1fa64acfd3c046f5a296ac80ddd8b925`.
The latter retains contact failure and its exact user decision. Five Python tests
and 19 Node tests passed, covering source/character/clip exclusion, strict view
comparison, independent acceptance, retained failures and baseline totals.

The pre-change full export completed at
`E:/proj/unusual/localset/tmp/m4-support-snapshot-20260927-v4`:
24/24 baseline identities, 24/24 related inventories, 24/24 alternative-view
inventories. Baseline stage acceptances remain 3; sampled passes remain projection
6, geometry 11, contact 9, occlusion 0, Runtime 24. This historical report does not
include the new policy family and must not be presented as its verification.
