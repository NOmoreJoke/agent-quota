import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

describe("transport boundary", () => {
  it("fails closed before dispatch when the payload is not in the command contract", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    const { invokeHost } = await import("./transport");
    await expect(invokeHost("accounts_read", { scope_ref: "all", url: "https://x" })).rejects.toThrow(
      "unknown field",
    );
    expect(invoke).not.toHaveBeenCalled();
  });
});
