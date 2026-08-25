# P5 real-sample motion goldens

`real-samples.approved.json` pins the exact P3, P4, and MotionIR inputs and the
deterministic P5 outputs for both See-through samples and both built-in clips.

The ordinary test suite validates the strict contract without requiring the
local immutable workspace. To rebuild every case through the secure readers,
publish/read back the exact five-document bundles, and prove that the workspace
did not change, run:

```powershell
$env:AUTOSPINE_VERIFY_REAL_P5_GOLDENS = "1"
python -m unittest tests.test_p5_motion_goldens
```

That opt-in test requires the approved P3, P4, MotionIR, and P5 bundle addresses
under `workspace/`. Change this file only after an intentional compiler or
contract revision and a reviewed real-sample regression.
