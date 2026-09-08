import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invokeHost } from "../host/transport";
import { useQuotaController } from "./useQuotaController";

vi.mock("../host/transport", () => ({ transportMode: "fixture", invokeHost: vi.fn() }));
const invoke = vi.mocked(invokeHost);
let controller: ReturnType<typeof useQuotaController>;
let root: Root;
let unmounted = false;

function Harness() {
  controller = useQuotaController();
  return null;
}

function response(command: string): Record<string, unknown> {
  if (command === "bootstrap_state") return { status: "ok", application_state: { offline: false } };
  if (command === "accounts_read") return { status: "ok", accounts: [{ principal_ref: "p-1", display_label: "DeepSeek", lifecycle: "active" }] };
  if (command === "quota_overview") return { status: "ok", projection: { capability_rows: [], freshness: "fresh" } };
  if (command === "scheduler_state") return { status: "ok", scheduler_state: { health: "absent", installed: false } };
  return { status: "ok", refresh_state: { phase: "completed" } };
}

beforeEach(async () => {
  unmounted = false;
  invoke.mockReset().mockImplementation(async (command) => response(command));
  const container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<Harness />));
});

afterEach(async () => {
  if (!unmounted) await act(async () => root.unmount());
  document.body.innerHTML = "";
});

describe("quota controller outcomes", () => {
  it("shows checking before bootstrap and unavailable on initial failure, then recovers without refreshing", async () => {
    await act(async () => root.unmount());
    let reject!: (reason: Error) => void;
    invoke.mockClear().mockImplementation((command) => command === "bootstrap_state"
      ? new Promise((_resolve, fail) => { reject = fail; })
      : Promise.resolve(response(command)));
    const container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    await act(async () => root.render(<Harness />));
    expect(controller.connection).toBe("checking");
    const initialCalls = invoke.mock.calls.length;
    await act(async () => controller.nativeCredential());
    expect(invoke).toHaveBeenCalledTimes(initialCalls);
    await act(async () => reject(new Error("not connected")));
    expect(controller.connection).toBe("unavailable");
    expect(controller.loading).toBe(false);
    await act(async () => controller.refresh());
    expect(invoke).toHaveBeenCalledTimes(initialCalls);
    invoke.mockClear().mockImplementation(async (command) => response(command));
    await act(async () => controller.retryLoad());
    expect(controller.connection).toBe("ready");
    expect(invoke.mock.calls.map(([command]) => command)).toEqual([
      "bootstrap_state", "accounts_read", "quota_overview", "scheduler_state",
    ]);
  });

  it("discards an action result after unmount without launching follow-up reads", async () => {
    let resolve!: (value: Record<string, unknown>) => void;
    invoke.mockClear().mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    let pending!: Promise<void>;
    await act(async () => { pending = controller.nativeCredential(); });
    await act(async () => root.unmount());
    unmounted = true;
    await act(async () => {
      resolve({ status: "ok", opaque_reference_status: "reference-created" });
      await pending;
    });
    expect(invoke).toHaveBeenCalledTimes(1);
    await controller.refresh();
    await controller.retryLoad();
    expect(invoke).toHaveBeenCalledTimes(1);
  });

  it("ignores deferred bootstrap data after unmount", async () => {
    let resolve!: (value: Record<string, unknown>) => void;
    invoke.mockClear().mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    let pending!: Promise<void>;
    await act(async () => { pending = controller.retryLoad(); });
    await act(async () => root.unmount());
    unmounted = true;
    await act(async () => {
      resolve(response("bootstrap_state"));
      await pending;
    });
    expect(invoke).toHaveBeenCalledTimes(4);
  });

  it("reports success only after the refreshed state loads", async () => {
    await act(async () => controller.refresh());
    expect(controller.refreshState.outcome).toBe("success");
    expect(controller.notice?.tone).toBe("success");
    expect(controller.busy).toBe(false);
  });

  it.each(["rejection", "error-dto"])("keeps cached accounts and reports reload %s after refresh", async (failure) => {
    invoke.mockImplementation(async (command) => {
      if (command === "accounts_read") {
        if (failure === "rejection") throw new Error("read failed");
        return { status: "error", accounts: [], safe_error: { code: "provider-unavailable" } };
      }
      return response(command);
    });
    await act(async () => controller.refresh());
    expect(controller.notice?.text).toContain("无法载入本机状态");
    expect(controller.notice?.tone).toBe("danger");
    expect(controller.refreshState.outcome).toBe("warning");
    expect(controller.accounts).toHaveLength(1);
    expect(controller.freshness).toBe("stale");
    expect(controller.busy).toBe(false);
  });

  it.each(["outcome-unknown", "provider-unavailable"])("does not claim success for %s", async (code) => {
    invoke.mockImplementation(async (command) => command === "refresh_scope"
      ? { status: "error", refresh_state: { phase: "failed" }, safe_error: { code } }
      : response(command));
    await act(async () => controller.refresh());
    expect(controller.refreshState.outcome).toBe("warning");
    expect(controller.notice?.tone).toBe("warning");
  });

  it("does not reload or auto-retry an unknown outcome", async () => {
    invoke.mockClear().mockResolvedValue({ status: "error", refresh_state: { phase: "failed" }, safe_error: { code: "outcome-unknown" } });
    await act(async () => controller.refresh());
    expect(invoke).toHaveBeenCalledTimes(1);
  });

  it("keeps background running distinct from completed", async () => {
    invoke.mockResolvedValue({ status: "ok", refresh_state: { phase: "running" } });
    await act(async () => controller.refresh());
    expect(controller.refreshState.phase).toBe("running");
    expect(controller.refreshState.outcome).toBe("none");
  });

  it.each(["refresh", "credential", "reauth", "delete", "purge", "export"])("handles rejected %s commands", async (action) => {
    invoke.mockRejectedValue(new Error("host rejected"));
    await act(async () => {
      if (action === "refresh") await controller.refresh();
      if (action === "credential") await controller.nativeCredential();
      if (action === "reauth") await controller.reauthenticate("p-1");
      if (action === "delete") await controller.destructive("delete", "p-1");
      if (action === "purge") await controller.destructive("purge", "selection-all-local-data");
      if (action === "export") await controller.exportRedacted();
    });
    expect(controller.notice).toEqual({ tone: "danger", text: expect.stringContaining("host rejected") });
    expect(controller.busy).toBe(false);
    if (action === "refresh") expect(controller.refreshState.outcome).toBe("error");
  });

  it("prevents overlapping actions even before React renders the disabled state", async () => {
    let resolve!: (value: Record<string, unknown>) => void;
    invoke.mockClear().mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    let pending!: Promise<void>;
    await act(async () => {
      pending = controller.refresh();
      await controller.refresh("p-1");
      await controller.destructive("delete", "p-1");
    });
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(controller.busy).toBe(true);
    await act(async () => {
      resolve(response("refresh_scope"));
      await pending;
    });
    expect(controller.busy).toBe(false);
  });

  it.each(["credential", "reauth", "delete", "purge"])("preserves reload failure after %s commit", async (action) => {
    invoke.mockImplementation(async (command) => {
      if (command === "accounts_read") throw new Error("reload failed");
      if (command === "credential_dialog_open") return { status: "ok", opaque_reference_status: "reference-created" };
      if (command === "destructive_confirmation_open") return { status: "committed" };
      return response(command);
    });
    await act(async () => {
      if (action === "credential") await controller.nativeCredential();
      if (action === "reauth") await controller.reauthenticate("p-1");
      if (action === "delete") await controller.destructive("delete", "p-1");
      if (action === "purge") await controller.destructive("purge", "selection-all-local-data");
    });
    expect(controller.notice?.text).toContain("无法载入本机状态");
    expect(controller.notice?.tone).toBe("danger");
  });

  it("does not reload after a cancelled destructive dialog", async () => {
    invoke.mockClear().mockResolvedValue({ status: "cancelled" });
    await act(async () => controller.destructive("delete", "p-1"));
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(controller.notice?.text).toBe("删除已取消。");
  });

  it.each([
    ["delete", "outcome-unknown"], ["purge", "outcome-unknown"],
    ["delete", "provider-unavailable"], ["purge", "provider-unavailable"],
    ["credential", "outcome-unknown"], ["credential", "provider-unavailable"],
    ["reauth", "outcome-unknown"],
  ])("keeps %s %s distinct from user cancellation", async (action, code) => {
    invoke.mockClear().mockResolvedValue({ status: "cancelled", safe_error: { code } });
    await act(async () => {
      if (action === "credential") await controller.nativeCredential();
      else if (action === "reauth") await controller.reauthenticate("p-1");
      else await controller.destructive(action as "delete" | "purge", "p-1");
    });
    expect(controller.notice?.tone).toBe("warning");
    expect(controller.notice?.text).toContain(code === "outcome-unknown" ? "结果未知" : "未完整完成");
    expect(controller.notice?.text).not.toMatch(/已取消|没有更改/);
    expect(controller.freshness).toBe("stale");
    expect(invoke).toHaveBeenCalledTimes(1);
  });

  it.each(["credential", "reauth"])("reloads committed %s metadata when the first provider query fails", async (action) => {
    invoke.mockImplementation(async (command) => {
      if (command === "credential_dialog_open") return { status: "cancelled", opaque_reference_status: "reference-created", safe_error: { code: "reauth-required" } };
      if (command === "reauthenticate") return { status: "error", reauth_state: "failed", safe_error: { code: "reauth-required" } };
      if (command === "accounts_read") return { status: "ok", accounts: [{ principal_ref: "new", display_label: "Kimi", lifecycle: "needs-reauth" }] };
      return response(command);
    });
    await act(async () => {
      if (action === "credential") await controller.nativeCredential();
      else await controller.reauthenticate("p-1");
    });
    expect(controller.accounts[0].principal_ref).toBe("new");
    expect(controller.accounts[0].lifecycle).toBe("needs-reauth");
    expect(controller.notice?.text).toContain("凭据已失效");
    expect(controller.notice?.tone).toBe("warning");
  });

  it.each(["completed", "cancelled", "failed"])("projects export %s", async (status) => {
    invoke.mockResolvedValue({ export_status: status });
    await act(async () => controller.exportRedacted());
    expect(controller.notice?.tone).toBe(status === "completed" ? "success" : status === "cancelled" ? "info" : "danger");
  });
});
