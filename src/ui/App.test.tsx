import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

vi.mock("../host/transport", () => ({
  transportMode: "fixture",
  invokeHost: vi.fn(async (command: string) => {
    if (command === "bootstrap_state") {
      return { application_state: { launch_state: "ready", offline: false }, status: "ok" };
    }
    if (command === "accounts_read") {
      return {
        accounts: [
          { display_label: "OpenAI", lifecycle: "active", principal_ref: "p-1" },
          { display_label: "Kimi Code Token Plan", lifecycle: "active", principal_ref: "p-2" },
          { display_label: "Kimi (中国区)", lifecycle: "active", principal_ref: "p-3" },
        ],
        status: "ok",
      };
    }
    if (command === "quota_overview") {
      return {
        projection: {
          capability_rows: [
            { capability_ref: "cap-1", display_kind: "window", health: "ok", value_display: "72%" },
            { capability_ref: "cap-kimi-code-weekly", display_kind: "window", health: "ok", value_display: "周剩余 0%" },
            { capability_ref: "cap-kimi-code-limit-0-5h", display_kind: "window", health: "ok", value_display: "5小时剩余 100%" },
            { capability_ref: "cap-kimi-code-row-555555555555555555555555-account-aaaaaaaaaaaaaaaaaaaaaaaa", display_kind: "window", health: "ok", value_display: "周剩余 0%" },
            { capability_ref: "cap-kimi-code-row-666666666666666666666666-account-aaaaaaaaaaaaaaaaaaaaaaaa", display_kind: "window", health: "ok", value_display: "5小时剩余 0%" },
            { capability_ref: "cap-kimi-code-row-111111111111111111111111-account-aaaaaaaaaaaaaaaaaaaaaaaa-weekly", display_kind: "window", health: "ok", value_display: "周剩余 0%" },
            { capability_ref: "cap-kimi-code-row-222222222222222222222222-account-aaaaaaaaaaaaaaaaaaaaaaaa-5h", display_kind: "window", health: "ok", value_display: "general · 剩余 0%剩余 100%" },
            { capability_ref: "cap-kimi-code-row-333333333333333333333333-account-bbbbbbbbbbbbbbbbbbbbbbbb-weekly", display_kind: "window", health: "ok", value_display: "周剩余 100%" },
            { capability_ref: "cap-kimi-code-row-444444444444444444444444-account-bbbbbbbbbbbbbbbbbbbbbbbb-5h", display_kind: "window", health: "ok", value_display: "5小时剩余 100%" },
            { capability_ref: "cap-kimi-code-injected", display_kind: "window", health: "ok", value_display: "赠送剩余 0%剩余 50%" },
            { capability_ref: "cap-kimi-code-empty", display_kind: "window", health: "ok", value_display: "加赠 80%剩余 0%" },
            { capability_ref: "cap-kimi-code-signed-zero", display_kind: "window", health: "ok", value_display: "旧缓存周剩余 -0%" },
            { capability_ref: "cap-kimi-code-unlimited", display_kind: "window", health: "ok", value_display: "旗舰剩余 0% · 周剩余 不限量" },
            { capability_ref: "cap-glm-limit", display_kind: "window", health: "ok", value_display: "5小时已用 100%" },
            { capability_ref: "cap-glm-mcp", display_kind: "window", health: "ok", value_display: "MCP月度已用 0%" },
            { capability_ref: "cap-glm-error", display_kind: "window", health: "error", value_display: "5小时已用 100%" },
            { capability_ref: "cap-minimax-cn-row-111111111111111111111111-account-aaaaaaaaaaaaaaaaaaaaaaaa-model-0-5h", display_kind: "window", health: "ok", value_display: "general · tier 80% · 5小时剩余 100%" },
            { capability_ref: "cap-minimax-cn-row-222222222222222222222222-account-bbbbbbbbbbbbbbbbbbbbbbbb-model-0-5h", display_kind: "window", health: "ok", value_display: "general · bonus剩余 0% · 5小时剩余 50%" },
            { capability_ref: "cap-minimax-cn-row-333333333333333333333333-account-bbbbbbbbbbbbbbbbbbbbbbbb-model-0-weekly", display_kind: "window", health: "ok", value_display: "general · bonus剩余 0% · 周剩余 不限量" },
            { capability_ref: "cap-minimax-cn-row-444444444444444444444444-account-aaaaaaaaaaaaaaaaaaaaaaaa-model-0-weekly", display_kind: "window", health: "ok", value_display: "general · tier 80% · 周剩余 0%" },
          ],
          freshness: "fresh",
          scope_ref: "scope-all",
        },
        status: "ok",
      };
    }
    if (command === "scheduler_state") {
      return { scheduler_state: { health: "healthy", installed: true }, status: "ok" };
    }
    return { status: "ok", refresh_state: { phase: "completed" } };
  }),
}));

afterEach(() => {
  document.body.innerHTML = "";
});

describe("App", () => {
  it("loads the overview and navigates all primary views", async () => {
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    await act(async () => root.render(<App />));
    await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
    expect(host.textContent).toContain("窗口额度 · 周 → 5小时");
    expect(host.querySelectorAll(".status-unavailable")).toHaveLength(3);
    expect(host.querySelectorAll(".status-error")).toHaveLength(1);
    const kimiRows = [...host.querySelectorAll(".provider-group")]
      .find((node) => node.querySelector(".provider-heading")?.textContent === "Kimi Code")
      ?.querySelectorAll<HTMLElement>(".quota-row");
    expect([...kimiRows ?? []].map((node) => node.querySelector(".subject")?.textContent)).toEqual([
      "周剩余 0%",
      "5小时剩余 100%",
      "赠送剩余 0%剩余 50%",
      "加赠 80%剩余 0%",
      "旧缓存周剩余 -0%",
      "旗舰剩余 0% · 周剩余 不限量",
      "周剩余 0%",
      "general · 剩余 0%剩余 100%",
      "周剩余 0%",
      "5小时剩余 0%",
      "周剩余 100%",
      "5小时剩余 100%",
    ]);
    expect([...kimiRows ?? []]
      .find((node) => node.querySelector(".subject")?.textContent === "5小时剩余 100%")
      ?.querySelector(".status")?.textContent).toContain("不可用");
    expect([...kimiRows ?? []]
      .find((node) => node.querySelector(".subject")?.textContent === "general · 剩余 0%剩余 100%")
      ?.querySelector(".status")?.textContent).toContain("不可用");
    const isolatedKimiRows = [...kimiRows ?? []].filter((node) =>
      node.getAttribute("aria-label")?.startsWith("5小时剩余 100%"),
    );
    expect(isolatedKimiRows.map((node) => node.querySelector(".status")?.textContent)).toEqual([
      "不可用", "可用",
    ]);
    expect(host.querySelector('[aria-label="周剩余 0% · 已用尽"]')).not.toBeNull();
    expect(host.querySelector('[aria-label="5小时剩余 100% · 不可用"]')).not.toBeNull();
    const quotaSearch = host.querySelector<HTMLInputElement>('[aria-label="搜索 Provider / Subject"]');
    await act(async () => {
      if (quotaSearch) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
        setter?.call(quotaSearch, "5小时");
        quotaSearch.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText" }));
      }
    });
    expect(host.querySelector('[aria-label="周剩余 0% · 已用尽"]')).toBeNull();
    expect(host.querySelector('[aria-label="5小时剩余 100% · 不可用"]')).not.toBeNull();
    await act(async () => {
      if (quotaSearch) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
        setter?.call(quotaSearch, "");
        quotaSearch.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward" }));
      }
    });
    const minimaxRows = [...host.querySelectorAll(".provider-group")]
      .find((node) => node.querySelector(".provider-heading")?.textContent === "MiniMax")
      ?.querySelectorAll<HTMLElement>(".quota-row");
    expect([...minimaxRows ?? []].map((node) => node.querySelector(".subject")?.textContent)).toEqual([
      "general · tier 80% · 周剩余 0%",
      "general · tier 80% · 5小时剩余 100%",
      "general · bonus剩余 0% · 周剩余 不限量",
      "general · bonus剩余 0% · 5小时剩余 50%",
    ]);
    expect([...minimaxRows ?? []][1]?.querySelector(".status")?.textContent).toContain("不可用");
    expect([...minimaxRows ?? []][3]?.querySelector(".status")?.textContent).toContain("可用");
    expect(host.querySelectorAll(".nav-item")).toHaveLength(5);

    const accounts = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("账户与 Provider"),
    );
    await act(async () => accounts?.click());
    expect(host.textContent).toContain("已启用 Provider");
    expect([...host.querySelectorAll(".provider-card h3")].map((node) => node.textContent)).toEqual([
      "OpenAI",
      "Kimi Code",
      "Kimi",
    ]);
    expect([...host.querySelectorAll("[data-provider-id]")].map((node) =>
      node.getAttribute("data-provider-id"),
    )).toEqual([
      "provider-026",
      "provider-034",
      "provider-035",
      "provider-038",
      "provider-073",
    ]);
    expect(host.querySelector('[aria-label^="Cursor "]')).toBeNull();

    const queue = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("刷新队列"),
    );
    await act(async () => queue?.click());
    expect(host.textContent).toContain("Global Refresh");
    expect(host.textContent).toContain("等待手动刷新");

    const status = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("状态"),
    );
    await act(async () => status?.click());
    expect(host.textContent).toContain("Renderer");
    expect(host.textContent).toContain("fixture scheduler_state: healthy");

    const settings = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("设置"),
    );
    await act(async () => settings?.click());
    expect(host.textContent).toContain("Provider 行为");
    root.unmount();
  });
});
