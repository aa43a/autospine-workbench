# Independent Studio Pose runtime addon

The addon supplies an isolated Windows x64 Python 3.14.3, seven fixed official
wheels and the pinned DWPose checkpoint. It is separate from both the Studio
client and the core engine distribution. No venv, global interpreter, engine
source, user project, observed pose or review record is copied into it.

`packaging/prepare_pose_runtime.py build` requires the official Python ZIP, an
offline wheelhouse, `packaging/pose-runtime-wheels.lock.json`, the fixed model,
the original fixed Hugging Face model card and the upstream DWPose license.
Every input is hash checked before assembly. The builder neither downloads
models nor installs packages into a global environment. Its `archive` command
creates and verifies a ZIP without replacing earlier releases.

The native contract is `autospine.pose-runtime-distribution/v1` in
`pose-distribution.json`. The allowed software roots are `python`, `models` and
`LICENSES`, plus `provenance.json`. The search path is fixed to the private
Python standard library, its vendored packages and its fixed bytecode-disabled
initialization archive. It contains no absolute developer or engine path.

The engine's fixed bootstrap explicitly adds its own trusted `src` directory
for the private worker. Model identity, real imports and the actual Pose runner
entrypoint are checked before the status becomes ready; business parameters
remain argv values. Dependency imports are rechecked instead of being cached
with model identity. The service process does not import inference packages.

Studio 0.3.10 adds native selection and installation. The complete inventory is
checked, streamed into a new profile-owned immutable `pb/v1` version, checked
again and probed before the paired interpreter/model settings are published.
The core must support this bootstrap and runtime environment session identity.
Current projects and stores are preserved; settings apply on the next launch.
Studio continues to own an OS-assigned loopback port without manual startup.

The model card at fixed Hugging Face revision
`1a7144101628d69ee7a3768d1ee3a094070dc388` declares `apache-2.0`. The corresponding
upstream declaration, original license and exact artifact URLs/hashes are
preserved; this does not assert licensing for every other checkpoint.
Python and wheel license texts remain in their original software roots.

Installation readiness is not image inference, correct joint placement or
human review. Real source preparation performs inference and returns joint
review with unreviewed points. Kimodo, Blender and official framebuffer capture
remain independent optional dependencies. Integrity inventories are not
publisher signatures. Full clean-machine S1–S6 qualification is still separate.

The package, engine bootstrap and native fixture tests are recorded with their
exact artifact versions in the client repository's `docs/VALIDATION.md`.
