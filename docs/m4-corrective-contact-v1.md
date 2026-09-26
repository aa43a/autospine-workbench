# Corrective contact recheck

2026-09-26. Alice Squat bundle
`418038c3621a71b2a56893f53862b0611ce1feb7e0b232f75e786d09ff29dcb2`
was measured again on all 3,713 final samples. No candidate or acceptance record
was changed.

The new `tools/m4_corrective_contact_audit.py` first checks the deform-only
relationship, exact character/source provenance, and existing Runtime sample
coverage. It binds source ankle trajectories to the original skeleton and then
measures the final skeleton, with unchanged bone definitions and bone tracks.

Results (`tmp/m4-corrective-link-v1/contact.json`):

- Moving ankle maximum error: 0.083511 px; limit 3.531407 px; passed.
- Inferred contact proxy maximum drift: 0.776676 px; status
  `inferred_proxy_passed`.
- Final skeleton: `bfd43de77aa435e84c61eb7e650f79b54e47738a1f645f6590b6c8c039d5a782`.

The exported final key is 1.8666670322418213 s versus integer-tick duration
1.866667 s. Contact and moving-ankle checks now permit at most one microsecond
of endpoint rounding, without changing actual sample times. Missing intervals,
nonfinite times, nonmonotonic grids and larger duration discrepancies still fail.

These are CPU bone proxies. They do not measure deformed shoe soles, GPU contact,
depth ordering or visual quality, and do not remove their pending checks.
The 12 tests across corrective contact, moving ankles and final contact pass.

## Workbench integration

Supplemental contact evidence can now be attached with the corrective linking
tool's `--contact-audit` option. The reader checks candidate, skeleton, Runtime
report and time-grid identity, finite measurements and consistent pass labels.
It exposes bounded numeric summaries without changing historical evidence.
The UI labels records with these checks and distinguishes missing checks from
passed/failed bone proxies. The original receipt and full audit travel with the
related-candidate export.

Registration `f7b87f685963fa6e10eade8efe75c88cbd9c33bc236507d4c2794150668cc2c4`
was appended and read back through the live workbench endpoint. It identifies
the same candidate as the earlier registration, reports 3,713 samples with both
bone-proxy checks passed, keeps `selected=false`, and retains mesh-sole contact,
depth and visual checks. The old registration remains readable and has no
supplemental check result. No visual acceptance was written.

Sixteen related-candidate tests and a pure JavaScript display check pass. Browser
interaction remains unverified because the browser permission check is unavailable;
the API check is not a substitute for that UI verification.
