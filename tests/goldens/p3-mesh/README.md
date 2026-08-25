# P3 mesh evidence goldens

The two approved JSON contracts pin the exact P2 inputs, P3 documents,
topology totals, continuous safe bend ranges, and visual artifact hashes for
the real See-through samples. The 17 MB of PNG evidence remains in the
content-addressed workspace bundle; the approved contracts bind every PNG by
both decoded RGBA and canonical encoded-byte SHA-256.

Normal tests validate the contracts without depending on local sample data.
To reproduce every mesh, probe, and PNG from the exact P2 bundles and compare
the result with these approvals, set `AUTOSPINE_VERIFY_REAL_P3_GOLDENS=1` and
run `python -m unittest tests.test_p3_mesh_goldens` from the repository root.
This verification is strictly read-only.
