export type Account = {
  display_label: string;
  last_error_code?: string;
  lifecycle: string;
  principal_ref: string;
};
export type Capability = {
  capability_ref: string;
  display_kind: string;
  health: string;
  value_display: string;
};
export type Scheduler = { health: string; installed: boolean };

export const providerOrder = ["GLM", "DeepSeek", "MiniMax", "Kimi", "Kimi Code", "其他"];

export function safeErrorMessage(code: string): string {
  if (code === "keychain-locked") return "macOS 登录钥匙串已锁定；解锁后再刷新";
  if (code === "reauth-required") return "Provider 凭据已失效；请重新认证";
  if (code === "provider-unavailable") return "Provider 暂时不可用";
  if (code === "timeout") return "Provider 请求超时";
  if (code === "contract-error") return "Provider 响应格式不受支持";
  return code;
}

export function providerName(reference: string): string {
  const value = reference.toLowerCase();
  if (value.includes("deepseek")) return "DeepSeek";
  if (value.includes("kimi-code")) return "Kimi Code";
  if (value.includes("kimi")) return "Kimi";
  if (value.includes("minimax")) return "MiniMax";
  if (value.includes("glm")) return "GLM";
  return "其他";
}

export function providerFromAccount(label: string): string {
  const value = label.toLowerCase();
  if (value.includes("deepseek")) return "DeepSeek";
  if (value.includes("kimi code")) return "Kimi Code";
  if (value.includes("kimi")) return "Kimi";
  if (value.includes("minimax")) return "MiniMax";
  if (value.includes("glm") || value.includes("z.ai")) return "GLM";
  return label;
}

type WindowMetric = { mode: "remaining" | "used"; percentage: number };

export function windowMetric(value: string): WindowMetric | null {
  const match = value.match(/(剩余|已用)\s*([+-]?\d+(?:\.\d+)?)%\s*$/u);
  if (!match) return null;
  const number = Number(match[2]);
  if (!Number.isFinite(number) || number < 0 || number > 100) return null;
  return { mode: match[1] === "剩余" ? "remaining" : "used", percentage: number };
}

export function displayedHealth(row: Capability): string {
  if (row.health !== "ok" || row.display_kind !== "window") return row.health;
  const metric = windowMetric(row.value_display);
  if (metric?.mode === "remaining" && metric.percentage === 0) return "exhausted";
  if (metric?.mode === "used" && metric.percentage === 100) return "exhausted";
  return row.health;
}

export function isWeeklyWindow(row: Capability): boolean {
  return row.display_kind === "window" && row.capability_ref.endsWith("-weekly");
}

function isFiveHourWindow(row: Capability): boolean {
  return row.display_kind === "window" && row.capability_ref.endsWith("-5h");
}

export function windowFamily(row: Capability): string {
  const model = row.capability_ref.match(
    /^cap-minimax-(?:cn|global)-row-[0-9a-f]{24}-account-([0-9a-f]{24})-model-(\d+)-(?:5h|weekly)$/u,
  );
  if (model) return `MiniMax:${model[1]}:model-${model[2]}`;
  const account = row.capability_ref.match(
    /-row-[0-9a-f]{24}-account-([0-9a-f]{24})(?:-(?:5h|weekly))?$/u,
  );
  return account ? `${providerName(row.capability_ref)}:${account[1]}` : providerName(row.capability_ref);
}

function windowOrder(row: Capability, sourceIndex: number): [string, number, number] {
  const model = row.capability_ref.match(/-account-([0-9a-f]{24})-model-(\d+)-/u);
  const account = row.capability_ref.match(
    /-row-[0-9a-f]{24}-account-([0-9a-f]{24})(?:-(?:5h|weekly))?$/u,
  );
  const familyOrder = model
    ? `${model[2].padStart(6, "0")}-${model[1]}`
    : account ? `000000-${account[1]}` : "0";
  const periodOrder = isWeeklyWindow(row) ? 0 : isFiveHourWindow(row) ? 1 : 2;
  return [familyOrder, periodOrder, sourceIndex];
}

export function compareWindowOrder(
  left: { row: Capability; sourceIndex: number },
  right: { row: Capability; sourceIndex: number },
): number {
  const a = windowOrder(left.row, left.sourceIndex);
  const b = windowOrder(right.row, right.sourceIndex);
  return a[0].localeCompare(b[0]) || a[1] - b[1] || a[2] - b[2];
}

export function effectiveHealth(row: Capability, exhaustedWeeklyFamilies: ReadonlySet<string>): string {
  const health = displayedHealth(row);
  if (health === "ok" && isFiveHourWindow(row) && exhaustedWeeklyFamilies.has(windowFamily(row))) {
    return "unavailable";
  }
  return health;
}
