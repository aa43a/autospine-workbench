import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const webRoot = new URL("../", import.meta.url);

test("main workbench keeps all save actions in a bounded narrow-screen row", async () => {
  const [html, css, app] = await Promise.all([
    readFile(new URL("index.html", webRoot), "utf8"),
    readFile(new URL("main-workbench-responsive.css", webRoot), "utf8"),
    readFile(new URL("app.js", webRoot), "utf8"),
  ]);

  assert.match(html, /href="\.\/main-workbench-responsive\.css"/);
  assert.match(html, /<div class="save-cluster">[\s\S]*id="motionPolicyReviewLink"[\s\S]*workflow-hub\.html[\s\S]*id="saveBtn"/);
  assert.match(app, /dom\.motionPolicyReviewLink\.href\s*=\s*`\.\/motion-policy-review\.html\?project=\$\{encodeURIComponent\(state\.selectedProjectId\)\}`/);
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*?\.topbar\s*{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*?\.save-cluster\s*{[^}]*display:\s*grid[^}]*grid-column:\s*1[^}]*grid-row:\s*4[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)[^}]*width:\s*100%/);
  assert.match(css, /\.save-cluster\s*>\s*\.button\s*{[^}]*min-width:\s*0[^}]*padding-inline:\s*8px/);
});
