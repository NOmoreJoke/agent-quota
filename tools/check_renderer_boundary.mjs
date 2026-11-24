import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { globSync } from "node:fs";

const forbidden = [
  /\bfetch\s*\(/,
  /\bXMLHttpRequest\b/,
  /\bWebSocket\b/,
  /\blocalStorage\b/,
  /\bsessionStorage\b/,
  /\bdocument\.cookie\b/,
  /\beval\s*\(/,
  /\bnew\s+Function\b/,
];

// Exact-file pins keep the exception limited to fixed light/dark and motion on/off preferences.
// Changes to these two audited storage adapters require an explicit boundary review.
const appearanceStoragePins = new Map([
  ["src/ui/appearancePreference.ts", "9caf163f9ec0f16bcdd310975d2df84fd1d2f8286d65b7fb2587084465e85f0a"],
  ["public/appearance-bootstrap.js", "824db1cfa7431b511c02b2364574c4fe00ea5e6f04c0b824d9fa66ce2107919f"],
]);

const allow = new Set(["src/host/transport.ts", "src/host/transport.test.ts"]);
const files = [...globSync("src/**/*.{ts,tsx}", { exclude: ["src/agent_quota/**"] }), ...globSync("public/**/*.js")];
const failures = [];
for (const file of files) {
  const source = readFileSync(file, "utf8");
  const storagePin = appearanceStoragePins.get(file);
  const pinnedAppearance = storagePin === createHash("sha256").update(source).digest("hex");
  if (storagePin && !pinnedAppearance) failures.push(`${file}: appearance storage boundary changed; review its fixed key and enum`);
  for (const pattern of forbidden) {
    if (pattern.source === String.raw`\blocalStorage\b` && pinnedAppearance) continue;
    if (pattern.test(source)) failures.push(`${file}: ${pattern}`);
  }
  if (!allow.has(file) && source.includes("@tauri-apps/api/core")) {
    failures.push(`${file}: direct Tauri invoke import`);
  }
}
if (failures.length) {
  process.stderr.write(`${failures.join("\n")}\n`);
  process.exit(1);
}
process.stdout.write(`renderer boundary PASS (${files.length} files)\n`);
