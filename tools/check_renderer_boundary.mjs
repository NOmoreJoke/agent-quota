import { readFileSync } from "node:fs";
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

const allow = new Set(["src/host/transport.ts", "src/host/transport.test.ts"]);
const files = globSync("src/**/*.{ts,tsx}", { exclude: ["src/agent_quota/**"] });
const failures = [];
for (const file of files) {
  const source = readFileSync(file, "utf8");
  for (const pattern of forbidden) {
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
