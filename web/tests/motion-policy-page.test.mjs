import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("page keeps a read-only Python preflight and accessible rendering boundary", async () => {
  const root = new URL("../", import.meta.url);
  const [html, css, app, view, api, hash, policyStep] = await Promise.all([
    readFile(new URL("motion-policy-review.html", root), "utf8"),
    readFile(new URL("motion-policy-review.css", root), "utf8"),
    readFile(new URL("modules/motion-policy-review-app.js", root), "utf8"),
    readFile(new URL("modules/motion-policy-review-view.js", root), "utf8"),
    readFile(new URL("modules/motion-policy-preflight-api.js", root), "utf8"),
    readFile(new URL("modules/motion-policy-hash.js", root), "utf8"),
    readFile(new URL("modules/motion-policy-policy-step.js", root), "utf8"),
  ]);
  assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1">/);
  assert.match(html, /class="skip-link"/);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.match(html, /href="\.\/workflow-hub\.html"/);
  assert.match(html, /不预填/);
  assert.match(html, /id="policySha"/);
  assert.match(html, /id="policyIdentitySha"/);
  assert.match(html, /本机 Python 只读预检/);
  assert.match(html, /零写入/);
  assert.match(html, /CLI 仍是最终/);
  assert.doesNotMatch(html, /\son[a-z]+\s*=/i);
  assert.doesNotMatch(`${app}\n${view}`, /innerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
  assert.doesNotMatch(`${hash}\n${policyStep}`, /canonicalSha256|canonicalJson/);
  assert.match(api, /\/api\/motion-policy\/preflight/);
  assert.match(api, /motion-policy-preflight-v1/);
  assert.match(api, /policy_json/);
  assert.match(api, /foot_candidates_json/);
  assert.doesNotMatch(api, /method:\s*"(?:PUT|PATCH|DELETE)"/);
  assert.match(css, /min-height:\s*44px/);
  assert.match(css, /@media \(max-width:\s*520px\)/);
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
});
