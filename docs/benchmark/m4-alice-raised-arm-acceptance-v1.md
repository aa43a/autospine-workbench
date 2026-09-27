# Alice independent raised-arm stage review

2026-09-27: user response "阶段可接受，保留遮挡异常" saved as revision 1,
`accepted_with_exceptions`, and the API confirmed `current_applies: true`.

- Job: `motion-f11c08d1f97e41268c06333b01b1b971`
- Artifact: `636831b4275e4b77e81235e30b2f5ef2844c46de51145e0ca51f2beb17cd6402`
- Evidence: `aa87fddef400246b78ede8c08a15c684a37a03a43a8a2d69ab97de8d1882be01`
- Scope: Alice, independent -30 degree view, single bent-arm raise.

Projection, geometry, contact and Runtime sampled checks passed. Arm/topwear
occlusion remains a technical failure; readiness is still `needs_changes`.
This receipt does not accept the fixed baseline, another character or motion,
and provides no production authorization.

The full support export was already running when this decision was saved.
Its per-record read times must be respected. Recheck this exact row after export,
preserving the original snapshot rather than silently treating it as current.
