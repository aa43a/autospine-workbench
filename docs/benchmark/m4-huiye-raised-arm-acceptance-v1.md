# Huiye independent raised-arm stage review

2026-09-27: user response "阶段可接受，保留遮挡异常和缺测" saved as revision 1,
`accepted_with_exceptions`; the live API confirmed `current_applies: true`.

- Job: `motion-32b455f6d40142a28d0d8844430bba20`
- Artifact: `ac4e5724a008b022255bc83792cfdf165850504dce22221ef06d459c2b7a8221`
- Evidence: `fb06f04330a54b4cca75d7b882bd23dec915578c4096268441d17b05414927f8`
- Scope: Huiye, independent -30 degree single bent-arm raise.

Projection, geometry, contact and Runtime sampled checks passed. Sleeve/torso
occlusion failures and missing measurements remain; readiness is `needs_changes`.
The decision does not change fixed-baseline counts or authorize production.

Live delivery subsequently verified all 88 ZIP members byte-for-byte against the
immutable artifact, plus player/contact/depth HTTP pages and stable job identity.
The receipt is `E:/proj/unusual/localset/tmp/m4-stage-accepted-delivery-v1/motion-32b455f6d40142a28d0d8844430bba20.json`.
This is not a new Runtime capture or browser-interaction validation.
