import { globSync, readFileSync } from "node:fs";

const markers = ["principal-openai-1", "fixtureInvoke", "VITE_AQ_FIXTURE_MODE=1"];
const files = globSync("dist/assets/*.js");
const failures = [];
for (const file of files) {
  const source = readFileSync(file, "utf8");
  for (const marker of markers) {
    if (source.includes(marker)) failures.push(`${file}: ${marker}`);
  }
}
if (files.length === 0 || failures.length > 0) {
  process.stderr.write(`${failures.join("\n") || "production bundle is missing"}\n`);
  process.exit(1);
}
process.stdout.write(`production fixture exclusion PASS (${files.length} chunks)\n`);
