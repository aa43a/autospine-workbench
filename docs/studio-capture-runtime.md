# Independent Studio animation-check runtime

The offline addon combines fixed Node.js 24.11.1, Playwright Core 1.58.2,
Spine core/webgl 4.3.13 and Chrome Headless Shell 145.0.7632.6 (Playwright
revision 1208). It is separate from Studio, the core engine and the Pose addon.
It contains no user browser/profile, engine source, project or trained model.

`packaging/prepare_capture_runtime.py build` accepts only the fixed official
archives recorded in its source. It checks their hashes before assembly,
checks the Node ZIP against the retained upstream checksum file, retains each
original license and records input origins. The `archive` command verifies
fixed software trees and all output ZIP bytes without replacing prior releases.
The manifest is `capture-distribution.json`, schema
`autospine.capture-runtime-distribution/v1`. Fixed versions and exact inventory
hashes cover the complete browser DLL/resource tree and all three JS packages;
version names or a launcher hash alone do not qualify a package.

Studio 0.3.11 supports native folder selection, stream-verified immutable
installation under its profile's `cb/v1` versions and simultaneous derivation
of the three capture configuration paths. Bundle selection and advanced manual
capture selections are mutually exclusive for the current save. Checks fail
without publishing settings, and current tasks keep their startup environment.
Saved settings apply only after reopening Studio. The engine owns its automatic
loopback service; the user does not start or select a port.

The matching core engine declares
`headless-shell-inprocess-gpu-task-log-v1`. On Windows the fixed Headless Shell's
GPU child does not initialize the browser's log target and otherwise writes
`debug.log` beside its executable. This fixed software capture therefore runs
the GPU service inside each task's browser and sends diagnostics to that task's
absolute `CHROME_LOG_FILE`. External Chrome/Edge preserve their separate GPU
behavior. This keeps installed software inventories unchanged; a GPU crash or
hang affects the whole task browser, so existing task isolation and deadlines
remain necessary. The complete capture tool hash binds the launch flags.

Relevant fixed upstream sources:

- [Playwright browser metadata](https://github.com/microsoft/playwright/blob/v1.58.2/packages/playwright-core/browsers.json)
- [Windows Headless logging initialization](https://raw.githubusercontent.com/chromium/chromium/145.0.7632.6/headless/lib/headless_content_main_delegate.cc)
- [GPU thread/process selection](https://raw.githubusercontent.com/chromium/chromium/145.0.7632.6/content/browser/gpu/gpu_process_host.cc)

Original Spine Runtime terms are retained in both packages; this addon does not
grant an editor license or replace upstream terms. An inventory is not a
publisher signature. Installing/configuring the addon is not actual animation
capture, geometric correctness or human stage acceptance. FBX/Blender and
Kimodo remain separate optional environments. Full ordinary/wide-sleeve
continuous workflow qualification remains distinct from package verification.
