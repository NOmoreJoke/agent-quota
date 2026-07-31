import type { CommandId } from "../contracts/renderer";

export type FixtureScenario =
  | "default"
  | "empty"
  | "offline"
  | "outcome-unknown"
  | "partial"
  | "reauth"
  | "refreshing";

function scenario(): FixtureScenario {
  const value = new URLSearchParams(window.location.search).get("scenario");
  const supported: FixtureScenario[] = [
    "default",
    "empty",
    "offline",
    "outcome-unknown",
    "partial",
    "reauth",
    "refreshing",
  ];
  return supported.includes(value as FixtureScenario) ? (value as FixtureScenario) : "default";
}

const accountRows = [
  { display_label: "OpenAI · 工作账户", lifecycle: "active", principal_ref: "principal-openai-1" },
  { display_label: "Codex · 本机", lifecycle: "active", principal_ref: "principal-codex-1" },
  { display_label: "Claude · 研究", lifecycle: "needs-reauth", principal_ref: "principal-claude-1" },
];

const addedAccountRows: typeof accountRows = [];

function addFixtureAccount(): void {
  if (addedAccountRows.length > 0) return;
  addedAccountRows.push({
    display_label: "Fixture · 临时测试账户",
    lifecycle: "active",
    principal_ref: "principal-fixture-test-1",
  });
}

const capabilityRows = [
  { capability_ref: "cap-five-hour", display_kind: "window", health: "ok", value_display: "5 小时窗口 · 72%" },
  { capability_ref: "cap-weekly", display_kind: "balance", health: "ok", value_display: "每周额度 · 44%" },
  { capability_ref: "cap-codex", display_kind: "status", health: "incompatible", value_display: "CLI 版本不兼容" },
];

export async function fixtureInvoke(commandId: CommandId, payload: Record<string, unknown>): Promise<unknown> {
  await new Promise((resolve) => setTimeout(resolve, commandId === "refresh_scope" ? 180 : 35));
  const mode = scenario();
  switch (commandId) {
    case "bootstrap_state":
      return {
        application_state: {
          launch_state: "ready",
          offline: mode === "offline",
        },
        status: "ok",
      };
    case "accounts_read":
      return {
        accounts: mode === "empty" ? addedAccountRows : [...accountRows, ...addedAccountRows],
        status: "ok",
      };
    case "quota_overview":
      return {
        projection: {
          capability_rows:
            mode === "partial"
              ? capabilityRows.map((row, index) =>
                  index === 1 ? { ...row, health: "error", value_display: "暂时不可用" } : row,
                )
              : capabilityRows,
          freshness: mode === "offline" ? "stale" : "fresh",
          scope_ref: String(payload.scope_ref ?? "scope-all"),
        },
        status: "ok",
      };
    case "refresh_scope":
      if (mode === "outcome-unknown") {
        return {
          refresh_state: { phase: "failed" },
          safe_error: { code: "outcome-unknown", retryable: false },
          status: "error",
        };
      }
      return {
        refresh_state: { phase: mode === "refreshing" ? "running" : "completed" },
        status: mode === "refreshing" ? "running" : "ok",
      };
    case "config_validate_apply":
      return { classification: "nondestructive-applied", status: "ok" };
    case "credential_dialog_open":
      addFixtureAccount();
      return { opaque_reference_status: "reference-created", status: "ok" };
    case "destructive_confirmation_open":
      return { status: "cancelled" };
    case "reauthenticate":
      return { reauth_state: mode === "reauth" ? "pending" : "succeeded", status: "ok" };
    case "export_redacted":
      return { export_status: "completed", status: "ok" };
    case "scheduler_state":
      return { scheduler_state: { health: "healthy", installed: true }, status: "ok" };
  }
}
