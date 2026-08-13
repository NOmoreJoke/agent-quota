import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const runtimeRoot = process.env.AQ_ACCEPTANCE_RUNTIME_ROOT;
if (!runtimeRoot || !path.isAbsolute(runtimeRoot)) {
  throw new Error("AQ_ACCEPTANCE_RUNTIME_ROOT must be an absolute isolated runtime path");
}
const require = createRequire(path.join(runtimeRoot, "package.json"));
const Ajv2020 = require("ajv/dist/2020");
const documentPath = path.resolve(process.argv[2] ?? path.join(root, "docs/acceptance-matrix-v2.json"));
const schemaPath = path.resolve(process.argv[3] ?? path.join(root, "docs/acceptance-matrix-v2.schema.json"));
const document = JSON.parse(fs.readFileSync(documentPath, "utf8"));
const schema = JSON.parse(fs.readFileSync(schemaPath, "utf8"));
const ajv = new Ajv2020({
  allErrors: true,
  strict: true,
  formats: { date: /^\d{4}-\d{2}-\d{2}$/u },
});
const validate = ajv.compile(schema);
const approvedClaimedCells = new Set([
  "deepseek-api-balance-cn/wallet_balance",
  "kimi-api-balance-cn/wallet_balance",
  "kimi-code-token-plan/window_5h",
  "kimi-code-token-plan/window_week",
  "kimi-code-token-plan/extra_usage_wallet_when_present",
  "minimax-token-plan-cn/window_5h",
  "minimax-token-plan-cn/window_week",
  "glm-coding-plan-cn/token_window_5h",
  "glm-coding-plan-cn/mcp_monthly_usage",
  "volcengine-ark-agent-plan-personal/window_5h",
  "volcengine-ark-agent-plan-personal/window_week",
]);
const approvedRequiredGates = new Set([
  "holder_live_lifecycle",
  "launch_scope_implementation",
  "developer_id_notarization",
  "final_package_evidence",
]);

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

invariant(validate(document), ajv.errorsText(validate.errors, { separator: "\n" }));
const products = document.products;
const capabilities = products.flatMap((product) => product.capabilities);
const gates = document.formal_release_gates;
const summary = document.scope_summary;
invariant(new Set(products.map((product) => product.product_id)).size === products.length, "duplicate product_id");
invariant(new Set(gates.map((gate) => gate.gate_id)).size === gates.length, "duplicate gate_id");
invariant(summary.product_card_count === products.length, "product count mismatch");
invariant(summary.brand_count === new Set(products.map((product) => product.brand)).size, "brand count mismatch");
invariant(summary.target_actionable_candidate_count === products.filter((product) => product.target_actionable_candidate).length, "target candidate count mismatch");
invariant(summary.current_creatable_count === products.filter((product) => product.current_creatable).length, "creatable count mismatch");
invariant(summary.implementation_blocked_candidate_count === products.filter((product) => product.target_actionable_candidate && !product.current_creatable).length, "implementation-blocked count mismatch");
invariant(summary.disabled_information_card_count === products.filter((product) => !product.target_actionable_candidate).length, "disabled card count mismatch");
for (const product of products) {
  invariant(!product.current_creatable || product.target_actionable_candidate, "creatable product is not a target candidate");
  invariant(!product.target_actionable_candidate || product.adapter_id !== null, "target candidate lacks adapter");
  invariant(new Set(product.capabilities.map((cell) => cell.capability_id)).size === product.capabilities.length, "duplicate product capability");
  for (const cell of product.capabilities) {
    invariant(document.allowed_statuses.includes(cell.status), "unknown capability status");
    invariant(cell.claimed === cell.release_denominator, "claimed/denominator mismatch");
    invariant(!cell.claimed || product.target_actionable_candidate, "disabled product claims capability");
  }
  if (!product.target_actionable_candidate) {
    invariant(product.adapter_id === null && !product.current_creatable, "disabled product has execution mapping");
    invariant(product.capabilities.every((cell) => !cell.claimed), "disabled product enters release denominator");
  }
}
for (const gate of gates) {
  invariant(document.formal_release_gate_allowed_statuses.includes(gate.status), "unknown gate status");
  if (gate.status === "PASS") {
    invariant(gate.commit_binding !== null && gate.evidence.length > 0, "PASS gate lacks commit-bound evidence");
  }
}
const claimedCells = new Set(products.flatMap((product) => product.capabilities
  .filter((cell) => cell.claimed && cell.release_denominator)
  .map((cell) => `${product.product_id}/${cell.capability_id}`)));
const requiredGates = new Set(gates.filter((gate) => gate.required).map((gate) => gate.gate_id));
invariant(claimedCells.size === approvedClaimedCells.size
  && [...claimedCells].every((identity) => approvedClaimedCells.has(identity)), "approved claimed capability set mismatch");
invariant(requiredGates.size === approvedRequiredGates.size
  && [...requiredGates].every((identity) => approvedRequiredGates.has(identity)), "approved required gate set mismatch");
const complete = capabilities.filter((cell) => cell.release_denominator).every((cell) => cell.status === "PASS")
  && gates.filter((gate) => gate.required).every((gate) => gate.status === "PASS");
process.stdout.write(`acceptance-matrix-v2 status=${complete ? "complete" : "blocked"}\n`);
