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
            { capability_ref: "cap-kimi-code-limit-0", display_kind: "window", health: "ok", value_display: "5小时剩余 100%" },
            { capability_ref: "cap-kimi-code-injected", display_kind: "window", health: "ok", value_display: "赠送剩余 0%剩余 50%" },
            { capability_ref: "cap-kimi-code-empty", display_kind: "window", health: "ok", value_display: "加赠 80%剩余 0%" },
            { capability_ref: "cap-kimi-code-signed-zero", display_kind: "window", health: "ok", value_display: "旧缓存周剩余 -0%" },
            { capability_ref: "cap-kimi-code-unlimited", display_kind: "window", health: "ok", value_display: "旗舰剩余 0% · 周剩余 不限量" },
            { capability_ref: "cap-glm-limit", display_kind: "window", health: "ok", value_display: "5小时已用 100%" },
            { capability_ref: "cap-glm-mcp", display_kind: "window", health: "ok", value_display: "MCP月度已用 0%" },
            { capability_ref: "cap-glm-error", display_kind: "window", health: "error", value_display: "5小时已用 100%" },
            { capability_ref: "cap-minimax-cn-general-5h", display_kind: "window", health: "ok", value_display: "general · 5小时剩余 100%" },
            { capability_ref: "cap-minimax-cn-video-5h", display_kind: "window", health: "ok", value_display: "video · 5小时剩余 50%" },
            { capability_ref: "cap-minimax-cn-video-weekly", display_kind: "window", health: "ok", value_display: "video · 周剩余 不限量" },
            { capability_ref: "cap-minimax-cn-general-weekly", display_kind: "window", health: "ok", value_display: "general · 周剩余 0%" },
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
    expect(host.querySelectorAll(".status-unavailable")).toHaveLength(2);
    expect(host.querySelectorAll(".status-error")).toHaveLength(1);
    const kimiRows = [...host.querySelectorAll(".provider-group")]
      .find((node) => node.querySelector(".provider-heading")?.textContent === "Kimi Code")
      ?.querySelectorAll<HTMLElement>(".quota-row");
    expect([...kimiRows ?? []].map((node) => node.querySelector(".subject")?.textContent)).toEqual([
      "周剩余 0%",
      "旧缓存周剩余 -0%",
      "旗舰剩余 0% · 周剩余 不限量",
      "5小时剩余 100%",
      "赠送剩余 0%剩余 50%",
      "加赠 80%剩余 0%",
    ]);
    expect([...kimiRows ?? []]
      .find((node) => node.querySelector(".subject")?.textContent === "5小时剩余 100%")
      ?.querySelector(".status")?.textContent).toContain("不可用");
    const minimaxRows = [...host.querySelectorAll(".provider-group")]
      .find((node) => node.querySelector(".provider-heading")?.textContent === "MiniMax")
      ?.querySelectorAll<HTMLElement>(".quota-row");
    expect([...minimaxRows ?? []].map((node) => node.querySelector(".subject")?.textContent)).toEqual([
      "general · 周剩余 0%",
      "general · 5小时剩余 100%",
      "video · 周剩余 不限量",
      "video · 5小时剩余 50%",
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
    expect(host.querySelectorAll("[data-provider-id]")).toHaveLength(78);
    expect(host.querySelector<HTMLButtonElement>('[aria-label="Cursor 不可添加"]')?.disabled).toBe(true);

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
