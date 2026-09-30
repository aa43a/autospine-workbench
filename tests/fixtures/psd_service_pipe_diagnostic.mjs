// Real private-Python diagnostic with Studio-like Node stdio ownership.
// No Electron, renderer, user state, fake decoder or production patch is used.
import { spawn } from "node:child_process";
import { mkdir, writeFile, readFile, realpath, lstat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
if (args.length < 4 || args.length > 5) throw Error("Expected private Python, bundle, PSD, new output path, optional no-watch/devnull control");
const [python, bundle, source, output] = args.slice(0, 4).map((item) => path.resolve(item));
const control = args[4] || "watch";
if (!["watch", "no-watch", "devnull"].includes(control)) throw Error("Invalid diagnostic control");
const fixtureRoot = path.dirname(fileURLToPath(import.meta.url));
const diagnosticRoot = await realpath(path.resolve(fixtureRoot, "../../release/test-results"));
const relative = path.relative(diagnosticRoot, output);
if (!relative || relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative))
  throw Error("Output must be below this engine repository's release/test-results");
let existing = output;
const equalPath = (first, second) => process.platform === "win32"
  ? first.toLowerCase() === second.toLowerCase() : first === second;
while (!equalPath(existing, diagnosticRoot)) {
  try {
    const info = await lstat(existing);
    if (info.isSymbolicLink() || !(info.isDirectory())) throw Error("Linked or invalid diagnostic output");
    if (!equalPath(await realpath(existing), existing))
      throw Error("Diagnostic output resolves outside its fixed location");
  } catch (error) { if (error.code !== "ENOENT") throw error; }
  existing = path.dirname(existing);
}
await mkdir(output, { recursive: false });
const fixture = path.join(fixtureRoot, "psd_service_diagnostic.py");
const childOutput = path.join(output, "private-service");
const command = ["-I", "-B", "-u", fixture, "--bundle", bundle, "--source", source,
  "--output", childOutput,
  ...(control === "no-watch" ? [] : ["--parent-stdin-watch"]),
  ...(control === "devnull" ? ["--worker-stdin-devnull"] : [])];
const started = performance.now();
const logs = { stdout: "", stderr: "" };
const report = { schema: "autospine.psd-service-pipe-diagnostic/v1", python, command,
  control,
  stdinReleaseAtMilliseconds: 32000, stdinRelease: null, processId: null,
  note: "Observed workload only; closes this owned child's parent stdin at 32s to compare with GUI quit." };
const child = spawn(python, command, {
  cwd: bundle,
  windowsHide: true,
  shell: false,
  stdio: ["pipe", "pipe", "pipe"],
  env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1" },
});
report.processId = child.pid;
child.stdout.on("data", (chunk) => {
  if (logs.stdout.length + chunk.length > 1048576) {
    report.outputLimit = true;
    child.kill();
    return;
  }
  logs.stdout += chunk.toString("utf8");
  process.stdout.write(chunk);
});
child.stderr.on("data", (chunk) => {
  if (logs.stderr.length + chunk.length > 1048576) {
    report.outputLimit = true;
    child.kill();
    return;
  }
  logs.stderr += chunk.toString("utf8");
});
child.stdin.on("error", (error) => { report.stdinError = error.code; });
const release = setTimeout(() => {
  report.stdinRelease = performance.now() - started;
  child.stdin.end("shutdown\n");
}, report.stdinReleaseAtMilliseconds);
const deadline = setTimeout(() => {
  report.forcedOwnedTermination = true;
  child.kill();
}, 70000);
const result = await new Promise((resolve) => {
  child.once("error", (error) => { report.spawnError = error.message; });
  child.once("close", (code, signal) => resolve({ code, signal }));
});
clearTimeout(release);
clearTimeout(deadline);
Object.assign(report, result, { elapsedMilliseconds: performance.now() - started });
await writeFile(path.join(output, "stdout.log"), logs.stdout);
await writeFile(path.join(output, "stderr.log"), logs.stderr);
try { report.service = JSON.parse(await readFile(path.join(childOutput, "report.json"), "utf8")); }
catch (error) { report.serviceReadError = error.message; }
await writeFile(path.join(output, "report.json"), JSON.stringify(report, null, 2) + "\n");
process.stdout.write(JSON.stringify({ event: "owned-child-exited", ...result,
  elapsedMilliseconds: report.elapsedMilliseconds, stdinRelease: report.stdinRelease }) + "\n");
process.exitCode = result.code === 0 ? 0 : 1;
