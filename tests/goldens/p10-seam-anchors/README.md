# P10.5a static seam candidate goldens

`real-samples.approved.json` pins the exact Layer Manifest/P3 addresses,
candidate SHA, relationship observability, attachment pairs, locator counts,
and region/mesh mix produced from the two real See-through samples.

Normal tests validate the approval file without reading local workspace
artifacts. To replay both exact inputs read-only and compare the complete
projection, set `AUTOSPINE_VERIFY_REAL_SEAM_GOLDENS=1` and run:

```powershell
python -m unittest tests.test_seam_anchor_goldens
```

These approvals cover static setup-alpha candidates only. They do not record
a human choice and do not prove dynamic or visual seam safety.
