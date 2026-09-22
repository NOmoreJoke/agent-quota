import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { invokeHost } from "../host/transport";
import { FloatingQuota } from "./FloatingQuota";

vi.mock("../host/transport", () => ({ transportMode: "fixture", invokeHost: vi.fn() }));
const invoke = vi.mocked(invokeHost);
let root: Root;
let host: HTMLDivElement;
const rows = [
  { capability_ref: "cap-glm-weekly", display_kind: "window", health: "ok", value_display: "周已用 25%" },
  { capability_ref: "cap-glm-5h", display_kind: "window", health: "ok", value_display: "5小时已用 10%" },
  { capability_ref: "cap-glm-balance", display_kind: "balance", health: "ok", value_display: "CNY 300.00" },
  { capability_ref: "cap-deepseek", display_kind: "balance", health: "ok", value_display: "CNY 125.00" },
  { capability_ref: "cap-minimax-weekly", display_kind: "window", health: "ok", value_display: "周剩余 0%" },
  { capability_ref: "cap-minimax-5h", display_kind: "window", health: "ok", value_display: "5小时剩余 100%" },
];
let snapshotRows = rows;
function button(label: string): HTMLButtonElement {
  return [...host.querySelectorAll("button")].find((node) => node.textContent === label)!;
}
function response(command: string): Record<string, unknown> {
  if (command === "bootstrap_state") return { status: "ok", application_state: { offline: false } };
  if (command === "accounts_read") return { status: "ok", accounts: [{ principal_ref: "p", display_label: "Test", lifecycle: "active" }] };
  if (command === "quota_overview") return { status: "ok", projection: { capability_rows: snapshotRows, freshness: "fresh" } };
  if (command === "scheduler_state") return { status: "ok", scheduler_state: { health: "absent", installed: false } };
  return { status: "ok", refresh_state: { phase: "completed" } };
}

beforeEach(async () => {
  snapshotRows = rows;
  vi.useFakeTimers();
  invoke.mockReset().mockImplementation(async (command) => response(command));
  host = document.createElement("div"); document.body.append(host); root = createRoot(host);
  await act(async () => root.render(<FloatingQuota />));
});
afterEach(async () => { await act(async () => root.unmount()); document.body.innerHTML = ""; vi.useRealTimers(); });

it("hover only reads snapshots, preserves window semantics and collapses after pointer departure", async () => {
  invoke.mockClear();
  const shell = host.querySelector(".floating-shell")!;
  await act(async () => { shell.dispatchEvent(new MouseEvent("pointerover", { bubbles: true })); vi.advanceTimersByTime(200); });
  expect(host.querySelector("#floating-details")).not.toBeNull();
  expect(invoke.mock.calls.map(([command]) => command)).toEqual(["bootstrap_state", "accounts_read", "quota_overview", "scheduler_state"]);
  const meters = [...host.querySelectorAll('[role="meter"]')];
  expect(meters.map((meter) => meter.getAttribute("aria-valuenow"))).toEqual(["90", "75"]);
  expect(host.querySelector(".floating-provider")?.textContent).not.toContain("CNY");
  await act(async () => button("MiniMax").click());
  expect([...host.querySelectorAll('[role="meter"]')].map((meter) => meter.getAttribute("aria-valuenow"))).toEqual(["100", "0"]);
  expect(host.querySelector('[aria-label="MiniMax"]')?.textContent).toContain("不可用");
  await act(async () => { shell.dispatchEvent(new MouseEvent("pointerout", { bubbles: true })); vi.advanceTimersByTime(400); });
  expect(host.querySelector("#floating-details")).toBeNull();
});

it("filters both kind and provider locally and remembers each view's selection", async () => {
  await act(async () => host.querySelector<HTMLButtonElement>(".floating-trigger")!.click());
  invoke.mockClear();
  expect([...host.querySelectorAll(".floating-provider-switch button")].map((node) => node.textContent)).toEqual(["GLM", "MiniMax"]);
  await act(async () => button("MiniMax").click());
  await act(async () => button("Wallet View").click());
  expect([...host.querySelectorAll(".floating-provider-switch button")].map((node) => node.textContent)).toEqual(["GLM", "DeepSeek"]);
  expect(host.querySelector(".floating-provider")?.textContent).toContain("CNY 300.00");
  expect(host.querySelectorAll('[role="meter"]')).toHaveLength(0);
  expect(host.textContent).not.toContain("5小时");
  await act(async () => button("DeepSeek").click());
  expect(host.querySelectorAll(".floating-provider")).toHaveLength(1);
  expect(host.querySelector(".floating-provider")?.textContent).toContain("CNY 125.00");
  expect(host.querySelector(".floating-provider")?.textContent).not.toContain("300.00");
  await act(async () => button("Window View").click());
  expect(button("MiniMax").getAttribute("aria-pressed")).toBe("true");
  expect(host.querySelector(".floating-provider")?.getAttribute("aria-label")).toBe("MiniMax");
  await act(async () => button("Wallet View").click());
  expect(button("DeepSeek").getAttribute("aria-pressed")).toBe("true");
  expect(invoke).not.toHaveBeenCalled();
});

it("falls back when the selected provider disappears and shows an empty category without mixing data", async () => {
  await act(async () => host.querySelector<HTMLButtonElement>(".floating-trigger")!.click());
  await act(async () => button("MiniMax").click());
  snapshotRows = rows.filter((row) => !row.capability_ref.includes("minimax"));
  await act(async () => button("刷新用量").click());
  expect(host.querySelector(".floating-provider")?.getAttribute("aria-label")).toBe("GLM");
  expect(button("GLM").getAttribute("aria-pressed")).toBe("true");
  snapshotRows = rows.filter((row) => row.display_kind === "balance");
  await act(async () => button("刷新用量").click());
  expect(host.textContent).toContain("暂无窗口额度");
  expect(host.querySelectorAll(".floating-provider-switch button")).toHaveLength(0);
  expect(host.querySelectorAll(".floating-provider")).toHaveLength(0);
  await act(async () => button("Wallet View").click());
  expect(host.querySelector(".floating-provider")?.textContent).toContain("CNY 300.00");
});

it("click refresh is one Provider request, pin keeps it open, Escape collapses and unknown outcomes survive reopening", async () => {
  await act(async () => host.querySelector<HTMLButtonElement>(".floating-trigger")!.click());
  invoke.mockClear().mockImplementation(async (command) => command === "refresh_scope"
    ? { status: "error", refresh_state: { phase: "failed" }, safe_error: { code: "outcome-unknown" } }
    : response(command));
  await act(async () => [...host.querySelectorAll("button")].find((button) => button.textContent === "刷新用量")!.click());
  expect(invoke.mock.calls.filter(([command]) => command === "refresh_scope")).toHaveLength(1);
  expect(host.textContent).toContain("刷新结果未知");
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="保持展开"]')!.click());
  const shell = host.querySelector(".floating-shell")!;
  await act(async () => { shell.dispatchEvent(new MouseEvent("pointerout", { bubbles: true })); vi.advanceTimersByTime(400); });
  expect(host.querySelector("#floating-details")).not.toBeNull();
  await act(async () => shell.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(host.querySelector("#floating-details")).toBeNull();
  await act(async () => { vi.advanceTimersByTime(2200); host.querySelector<HTMLButtonElement>(".floating-trigger")!.click(); });
  expect(host.textContent).toContain("刷新结果未知");
  expect(invoke.mock.calls.filter(([command]) => command === "refresh_scope")).toHaveLength(1);
});
