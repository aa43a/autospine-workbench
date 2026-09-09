import assert from "node:assert/strict";
import test from "node:test";
import { createWorkbenchAnimated } from "../modules/workbench-animated-controller.js";
import { readAnimatedRebase, rebaseItemDescription } from "../modules/workbench-animated-rebase.js";

const SHA = "1".repeat(64), REGISTRATION = "2".repeat(64), tick = () => new Promise((resolve) => setImmediate(resolve));
function harness(options = {}) {
  let stale = true;
  const context = { projectId: "alice", resolvedSha: SHA }, requests = [], models = [];
  const controller = createWorkbenchAnimated(null, { context: () => context,
    apiRequest: async (url, request = {}) => {
      requests.push({ url, request });
      if (url.endsWith("/rebase")) { if (options.rebase) await options.rebase(); stale = false; return {}; }
      if (url.endsWith("/preview")) return { schema: "autospine.animated-web-job/v1", authority: "none", project_id: context.projectId,
        job_id: `job-${"a".repeat(32)}`, status: "blocked", reason_code: "animated_review_required" };
      return { schema: "autospine.animated-overview/v1", project_id: context.projectId, resolved_project_sha256: context.resolvedSha,
        can_build: !stale, reason_code: stale ? "animated_source_stale" : null, clips: [{ id: "limb-flex-15", label: "屈伸" }], review_items: [],
        ...(stale ? { source_rebase: { status: options.status || "ready", expected_registration_sha256: REGISTRATION,
          changed_joint_ids: ["elbow.left"], unsupported_items: [] } } : {}) };
    },
  }, { view: { render: (model) => models.push(model) } });
  return { controller, context, requests, model: () => models.at(-1) };
}
test("source synchronization is never automatic and explicit action binds both exact identities", async () => {
  const h = harness(); h.controller.sync(); await tick();
  assert.equal(h.model().canStart, false); assert.equal(h.model().canRebase, true);
  await h.controller.refresh(); await h.controller.start();
  assert.equal(h.requests.filter((r) => r.request.method === "POST").length, 0);
  await h.controller.rebase();
  const posts = h.requests.filter((r) => r.request.method === "POST");
  assert.equal(posts.length, 2); assert.ok(posts[0].url.endsWith("/rebase")); assert.ok(posts[1].url.endsWith("/preview"));
  assert.deepEqual(JSON.parse(posts[0].request.body), { expected_resolved_sha256: SHA, expected_registration_sha256: REGISTRATION });
  assert.equal(posts[0].request.headers["X-Autospine-Intent"], "pipeline-preview");
  assert.match(h.model().reviewNotice, /重新复核/); assert.equal(h.context.resolvedSha, SHA);
});
test("unsupported and unsaved authoring states block synchronization without sending a mutation", async () => {
  const blocked = harness({ status: "blocked" }); blocked.controller.sync(); await tick(); await blocked.controller.rebase();
  assert.equal(blocked.model().canRebase, false); assert.equal(blocked.requests.filter((r) => r.request.method === "POST").length, 0);
  const dirty = harness(); dirty.controller.sync(); await tick(); dirty.context.dirty = true; dirty.controller.sync(); await dirty.controller.rebase();
  assert.equal(dirty.requests.filter((r) => r.request.method === "POST").length, 0);
});
test("switching projects during rebase ignores the old response and never starts a new-project animation", async () => {
  let done; const wait = new Promise((resolve) => { done = resolve; });
  const h = harness({ rebase: () => wait }); h.controller.sync(); await tick();
  const save = h.controller.rebase(); h.context.projectId = "crino"; h.controller.sync(); await tick(); done(); await save;
  assert.equal(h.requests.filter((r) => r.url.endsWith("/preview")).length, 0);
  assert.equal(h.model().reviewNotice, ""); assert.equal(h.model().downloadUrl, null);
});
test("malformed rebase registration and migration shape are rejected", () => {
  assert.equal(readAnimatedRebase(undefined), null);
  assert.throws(() => readAnimatedRebase({ status: "ready", expected_registration_sha256: "../../private", changed_joint_ids: [], unsupported_items: [] }));
  assert.throws(() => readAnimatedRebase({ status: "ready", expected_registration_sha256: REGISTRATION, changed_joint_ids: "elbow.left", unsupported_items: [] }));
});
test("unsupported synchronization identifies its entity and human-readable field", () => {
  const text = rebaseItemDescription({ joint_id: "elbow.left", field: "x", reason_code: "unsupported_override" });
  assert.match(text, /elbow.left/); assert.match(text, /水平坐标/); assert.match(text, /校正仍保留/);
  assert.doesNotMatch(text, /QA 报告/);
});
