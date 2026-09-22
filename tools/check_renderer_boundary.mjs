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

// Exact-file pins keep the exception limited to one fixed light/dark preference.
// Changes to these two audited storage adapters require an explicit boundary review.
const appearanceStoragePins = new Map([
  ["src/ui/appearancePreference.ts", "a037d47a1379db78278533176e793669e88bd11bc2927880f67356865162934f"],
  ["public/appearance-bootstrap.js", "b52ed47fc6d52178de96763e6e01a7cbc494a754c06ae01bb4f4f50bffdb4c36"],
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
