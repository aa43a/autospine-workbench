# Sleeve review from the workbench

After rebuilding a sleeve candidate, the sleeve panel provides two links:

- **打开修正时间轴** opens the latest completed geometry stage (`repair`, then
  `cuff` or `boundary` for older runs). Blocked geometry remains inspectable.
- **查看官方捕获与重叠** opens the verified framebuffer report and its local
  images when that stage completed.

The user does not enter an artifact address or a filesystem path. URLs are scoped
to the project and job. The server checks the saved project/draft identity, the
candidate withdrawal state, completed stage inventory and every returned file's
receipt digest. Only HTML, JSON and PNG from the fixed review stages are served;
unlisted files and paths outside the project/stage fail closed. A withdrawn
candidate's existing review URLs also stop serving until restored.

The links do not approve candidates or grant publication rights. A successful
framebuffer contact result still has the scope described in that report.

Validation covers cross-project access, traversal/unlisted paths, tampered bytes,
withdrawal, completed-stage selection and actual frontend link generation/restoration.
Real workbench job `job-1a2a127e3ff04cad9f3e838e7077a8f3` completed for Bayunlan.
Timeline, framebuffer HTML and PNG returned HTTP 200 through the scoped routes.
A real browser moved the timeline to sample 24/32 with two SVG regions, loaded
all 22 capture-review images, and reported zero page script errors.
104 sleeve tests, 11 panel tests and three source-size checks passed.

The attempted additional sample at `tmp/r3s-frozen-validation/yaomeng` was
subsequently identified by the user as sleeveless. It is **not** an accepted
sleeve validation input. The proposed 714-triangle draft remains unadopted;
the entry page now explains non-applicability. The exact user classification is
recorded in `f232a792eb9788b93d3cf999c8404661db2b234f4f6c5fb352214f035df85412.json`.
The prior page is retained as `unreviewed-proposal.html`, not as positive evidence.
An additional actual wide-sleeve asset is still required for the frozen-policy test.
