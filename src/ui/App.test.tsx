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
    expect(host.textContent).toContain("窗口使用率 · 降序");

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

    const queue = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("刷新队列"),
    );
    await act(async () => queue?.click());
    expect(host.textContent).toContain("Provider / Subject");

    const status = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("状态"),
    );
    await act(async () => status?.click());
    expect(host.textContent).toContain("Renderer");

    const settings = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("设置"),
    );
    await act(async () => settings?.click());
    expect(host.textContent).toContain("Provider 行为");
    root.unmount();
  });
});
