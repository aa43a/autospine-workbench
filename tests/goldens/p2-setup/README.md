# P2 setup visual goldens

These files are manually approved canonical setup renders for the two real
See-through samples. They are immutable review evidence, not output fixtures
that tests may regenerate or update automatically.

Each JSON contract binds the reviewed project, RigIR bundle, renderer,
encoder, decoded RGBA hash, and exact canonical PNG bytes. Verify one with:

```powershell
python -m autospine_workbench verify-setup-golden <rig-bundle> <approved.json>
```

Replacing a PNG or contract requires a new visual review and a normal source
control diff. The verification command is strictly read-only.
