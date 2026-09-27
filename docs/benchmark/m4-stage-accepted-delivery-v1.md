# Delivery checks for newly stage-accepted independent candidates

2026-09-27: `tools/m4_motion_delivery_check.py` downloaded each candidate from the
live workbench and checked the ZIP inventory and every member byte against its
immutable artifact. Player/contact/depth pages returned HTML, readiness matched
the artifact, and candidate identity was unchanged before/after download.

| Candidate job | Files | Technical readiness | ZIP SHA-256 |
| --- | ---: | --- | --- |
| `motion-c22f2a09ce804829ab7cc9a4ecf0ebbd` (Hongmeiling raised arm) | 91 | stage_review | `b36b6c33e41d88deb983881c07279e2e7dfdb6b37a9d5cbf95e29f2eb939c2f4` |
| `motion-1fa64acfd3c046f5a296ac80ddd8b925` (Hongmeiling Reach) | 92 | needs_changes | `c8342117f25924722e4116b912c52f720c63e6f489448649332fec45802becdb` |
| `motion-f11c08d1f97e41268c06333b01b1b971` (Alice raised arm) | 98 | needs_changes | `f8d7f4a23a781111604822a8c139d2a49a35a7e3605254b5e71941f2b5bbf0b4` |

Total: 281 exact files. Receipts including candidate hashes, page hashes, Runtime
inventory and UTC check times are preserved under
`E:/proj/unusual/localset/tmp/m4-stage-accepted-delivery-v1/`, named by job ID.

These are HTTP delivery and byte-identity checks, not new animation captures or
browser interaction tests. Existing stage acceptances and technical exceptions
remain separate: Reach contact drift and Alice occlusion are not cleared. No
fixed baseline is replaced and no production permission is granted.
