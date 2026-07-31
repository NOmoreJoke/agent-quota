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
        accounts: [{ display_label: "OpenAI", lifecycle: "active", principal_ref: "p-1" }],
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
    expect(host.textContent).toContain("当前额度");

    const accounts = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("账户管理"),
    );
    await act(async () => accounts?.click());
    expect(host.textContent).toContain("账户与认证");

    const settings = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("设置"),
    );
    await act(async () => settings?.click());
    expect(host.textContent).toContain("清理本机数据");
    root.unmount();
  });
});
