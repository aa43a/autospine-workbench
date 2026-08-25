# P4 IK evidence goldens

The two approved JSON contracts pin the complete nine-digest P3 input
identity, the immutable P4 profile/probe/bundle address, all four canonical
handle bend directions and kinematic reach annuli, and the numerical probe
totals for the real See-through samples. The full profile and probe documents
remain in the content-addressed workspace bundle; their SHA-256 identities bind
all solver geometry and every evaluated case without checking generated data
into Git.

Normal tests validate these contracts without depending on local sample data.
To rebuild the profile and probes from the exact P3 bundle, strictly re-read the
exact P4 bundle, compare both paths with these approvals, and prove the state
tree remains byte-for-byte unchanged, set
`AUTOSPINE_VERIFY_REAL_P4_GOLDENS=1` and run
`python -m unittest tests.test_p4_ik_goldens` from the repository root. This
verification is strictly read-only and never resolves a `latest` alias.
