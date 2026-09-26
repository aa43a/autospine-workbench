# Related candidate player loading

2026-09-26. Related player HTML, CSS and application scripts previously called
the full candidate loader before serving static assets. That repeatedly read and
validated every diagnostic file in a candidate bundle, even though those static
responses contained no candidate data. The current Alice Squat bundle is about
258 MB before compression.

Static responses now verify the immutable registration and its current request
and baseline, and defer the complete bundle/evidence inspection until scene or
Runtime data is requested. Scene content, textures, context, Runtime delivery,
reports and exports retain their existing complete validation. A corrupted
candidate may show the player shell, but its data still fails to load. This does
not select a candidate, change an acceptance record or relax a geometry gate.

Twenty-one focused Python tests passed. New coverage checks that static delivery
does not read whole bundles; changed requests/baselines and corrupt registrations
are rejected; scene content stays identical; corrupt textures and changed
evidence cannot reach scene, context, Runtime, reports or exports.

Browser interaction remains unverified: the supported browser tool reports that
saved browser permissions cannot be verified. The user's settings screenshot
shows both default browsing and downloads already set to Always allow. This is
not evidence that a site permission is turned off. No alternate browser was used
to bypass this check. The last service check also found no listener on port 8918;
there is no before/after live timing claim or fresh GPU capture for this change.

The fixed M4 matrix remains three characters by eight motions. The latest saved
API audit (`tmp/m4-cohort-current-20260926.json`) has 24 technical `needs_changes`
results, and three applicable breathing `accepted_with_exceptions` decisions.
Other candidates have no independent visual acceptance. Existing Runtime
evidence was read, not recaptured; this loading change does not complete M4.
