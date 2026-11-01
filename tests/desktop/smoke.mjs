// Native launch smoke: no UI automation, no credentials, no domain mutations.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile, stat, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const workspace = process.cwd();
const target = process.env.CARGO_TARGET_DIR ?? resolve(workspace, "apps/studio-web/src-tauri/target");
const binary = resolve(target, "release/bundle/macos/Chemistry Studio.app/Contents/MacOS/chemistry-studio-desktop");
const logPath = resolve(workspace, ".runtime/desktop/runtime.log");
const evidence = resolve(workspace, ".runtime/evidence/native/native-smoke.json");
const pause = (ms) => new Promise((done) => setTimeout(done, ms));
async function identity(port) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/desktop/runtime`, { signal: AbortSignal.timeout(1000) });
    return response.ok ? await response.json() : null;
  } catch { return null; }
}
async function health(port) {
  try { return (await fetch(`http://127.0.0.1:${port}/healthz`, { signal: AbortSignal.timeout(1000) })).ok; }
  catch { return false; }
}
async function until(check, timeout, message) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const result = await check();
    if (result) return result;
    await pause(250);
  }
  throw new Error(message);
}

assert.equal(process.platform, "darwin", "This smoke test requires macOS.");
assert.equal(await health(8788), false, "Port8788 is already active; leave it intact and quit its owning app before testing a cold launch.");
const unrelatedBefore = await health(8787);
const offset = await stat(logPath).then((file) => file.size).catch(() => 0);
const env = { ...process.env, PATH: "/usr/bin:/bin:/usr/sbin:/sbin" };
for (const key of Object.keys(env)) if (key.startsWith("STUDIO_")) delete env[key];
const child = spawn(binary, [], { cwd: workspace, env, stdio: ["ignore", "pipe", "pipe"] });
let output = "";
child.stdout.on("data", (value) => { output = (output + String(value)).slice(-8000); });
child.stderr.on("data", (value) => { output = (output + String(value)).slice(-8000); });
let launchError;
child.on("error", (error) => { launchError = error; });
let report;
try {
  const ready = await until(async () => {
    if (launchError) throw launchError;
    assert.equal(child.exitCode, null, `Native app exited during startup: ${output}`);
    const result = await identity(8788);
    return result?.application === "chemistry-studio" && typeof result.buildId === "string" && result.databaseReady === true && result.frontendAvailable === true ? result : null;
  }, 120_000, "The native app did not start its dedicated local backend.");
  await until(async () => (await readFile(logPath, "utf8")).slice(offset).includes("Bundled startup UI verified the runtime and opened the local workspace."), 20_000, "The bundled startup UI did not complete its native IPC→local workspace handoff.");
  assert.equal((await stat(resolve(workspace, ".runtime/desktop"))).mode & 0o777, 0o700);
  assert.equal((await stat(logPath)).mode & 0o777, 0o600);
  const html = await fetch("http://127.0.0.1:8788/");
  assert.match(html.headers.get("content-type") ?? "", /text\/html/);
  assert.match(await html.text(), /<div id="root">/);
  report = { checkedAt: new Date().toISOString(), binary, origin: "http://127.0.0.1:8788", identity: ready, finderLikePath: true, bundledStartupIpcConfirmed: true, privateLogModes: true };
} finally {
  if (child.exitCode === null && !launchError) {
    child.kill("SIGTERM");
    await until(() => child.exitCode !== null || child.signalCode !== null, 10_000, "Native app did not quit after its normal termination request.");
  }
}
await until(async () => !(await health(8788)), 5000, "The owned native backend remained running after app quit.");
assert.equal(await health(8787), unrelatedBefore, "The unrelated development service was changed by native app quit.");
report.ownedBackendReleasedOnQuit = true;
report.unrelatedDevelopmentServerPreserved = true;

// A separately owned, verified desktop service must survive app quit.
const existing = spawn(resolve(workspace, ".venv/bin/python"), ["-m", "uvicorn", "studio.api.app:create_app", "--factory", "--host", "127.0.0.1", "--port", "8788"], {
  cwd: workspace, stdio: "ignore", env: { ...env, STUDIO_PORT: "8788", STUDIO_ALLOWED_ORIGINS: "http://127.0.0.1:8788,http://localhost:8788", STUDIO_DESKTOP_FRONTEND_DIR: resolve(binary, "../../Resources/frontend"), STUDIO_DESKTOP_BUILD_ID: report.identity.buildId, STUDIO_VAULT_ROOT: resolve(workspace, ".runtime/vault") },
});
let reuseApp;
try {
  await until(async () => {
    assert.equal(existing.exitCode, null, "The separate fixture backend exited before reuse could be checked.");
    return (await identity(8788))?.databaseReady;
  }, 15_000, "The separate fixture backend did not become ready.");
  const reuseOffset = (await stat(logPath)).size;
  reuseApp = spawn(binary, [], { cwd: workspace, env, stdio: "ignore" });
  await until(async () => {
    assert.equal(reuseApp.exitCode, null, "Native app exited while reusing the existing backend.");
    const log = (await readFile(logPath, "utf8")).slice(reuseOffset);
    return log.includes("Reusing verified Chemistry Studio") && log.includes("Bundled startup UI verified the runtime and opened the local workspace.");
  }, 15_000, "Native app did not reuse the verified existing backend.");
  reuseApp.kill("SIGTERM");
  await until(() => reuseApp.exitCode !== null || reuseApp.signalCode !== null, 10_000, "Native app did not quit during backend reuse.");
  assert.equal(existing.exitCode, null, "App quit stopped a backend it did not own.");
  assert.equal((await identity(8788))?.databaseReady, true, "The reused backend did not remain ready after app quit.");
  report.verifiedExistingBackendReused = true;
  report.reusedBackendPreservedOnQuit = true;
} finally {
  if (reuseApp?.exitCode === null) reuseApp.kill("SIGTERM");
  if (existing.exitCode === null) {
    existing.kill("SIGTERM");
    await until(() => existing.exitCode !== null || existing.signalCode !== null, 10_000, "The fixture backend did not stop after test cleanup.");
  }
}
await until(async () => !(await health(8788)), 5000, "Fixture backend port did not close after smoke cleanup.");
await mkdir(resolve(workspace, ".runtime/evidence/native"), { recursive: true });
await writeFile(evidence, `${JSON.stringify(report, null, 2)}\n`);
console.log("Native smoke passed: Finder-like launch, ready database, bundled UI IPC handoff, private logs, owned backend cleanup, unrelated service preserved, verified existing backend reused and preserved.");
