import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, mkdirSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, dirname } from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const checker = resolve(root, "tools/check_renderer_boundary.mjs");
const adapters = ["src/ui/appearancePreference.ts", "public/appearance-bootstrap.js"];
function check(mutate) {
  const directory = mkdtempSync(resolve(tmpdir(), "aq-renderer-boundary-"));
  try {
    for (const file of adapters) {
      mkdirSync(dirname(resolve(directory, file)), { recursive: true });
      writeFileSync(resolve(directory, file), readFileSync(resolve(root, file)));
    }
    mutate(directory);
    return spawnSync(process.execPath, [checker], { cwd: directory, encoding: "utf8" });
  } finally { rmSync(directory, { recursive: true, force: true }); }
}

test("only the reviewed fixed-key enum adapters receive the storage exception", () => {
  assert.equal(check(() => {}).status, 0);
  for (const file of adapters) {
    const result = check((directory) => writeFileSync(resolve(directory, file), readFileSync(resolve(root, file), "utf8").replaceAll("agent-quota.appearance.v1", "other-sensitive-data")));
    assert.equal(result.status, 1);
    assert.match(result.stderr, /appearance storage boundary changed/);
  }
});

test("storage in another module and any network API remain forbidden", () => {
  for (const source of ['window.localStorage.getItem("agent-quota.appearance.v1")', 'window.sessionStorage.setItem("x", "y")', 'fetch("https://example.test")']) {
    const result = check((directory) => writeFileSync(resolve(directory, "src/untrusted.ts"), source));
    assert.equal(result.status, 1);
    assert.match(result.stderr, /src\/untrusted.ts/);
  }
});
