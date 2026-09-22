import { describe, expect, it, vi } from "vitest";
import { createAppearanceStore, type AppearancePorts } from "./appearanceStore";
import { type Appearance } from "./appearancePreference";

function harness(saved: Appearance | null = null) {
  let persisted = saved;
  const receivers = new Set<(value: unknown) => void>();
  const ports: AppearancePorts = {
    read: () => persisted,
    write: vi.fn((value) => { persisted = value; return true; }),
    apply: vi.fn(),
    broadcast: vi.fn(async (value) => { receivers.forEach((receive) => receive(value)); }),
    listen: vi.fn(async (receive) => { receivers.add(receive); return () => { receivers.delete(receive); }; }),
  };
  return { ports, receivers, commit: (value: Appearance) => { persisted = value; } };
}

describe("appearance store", () => {
  it("defaults to light and restores the persisted theme for a restarted window", () => {
    const { ports } = harness();
    const first = createAppearanceStore(ports);
    expect(first.getSnapshot().theme).toBe("light");
    first.setTheme("dark");
    expect(createAppearanceStore(ports).getSnapshot().theme).toBe("dark");
  });

  it("synchronizes two windows without re-broadcasting or persisting received events", async () => {
    const { ports } = harness();
    const first = createAppearanceStore(ports);
    const second = createAppearanceStore(ports);
    const stopFirst = first.subscribe(vi.fn());
    const stopSecond = second.subscribe(vi.fn());
    await Promise.resolve();
    first.setTheme("dark");
    expect(first.getSnapshot().theme).toBe("dark");
    expect(second.getSnapshot().theme).toBe("dark");
    second.setTheme("light");
    expect(first.getSnapshot().theme).toBe("light");
    expect(ports.write).toHaveBeenCalledTimes(2);
    expect(ports.broadcast).toHaveBeenCalledTimes(2);
    stopFirst(); stopSecond();
  });

  it("rejects invalid payloads and never replaces the latest preference with a delayed event", async () => {
    const { ports, receivers, commit } = harness("dark");
    const store = createAppearanceStore(ports);
    const stop = store.subscribe(vi.fn());
    await Promise.resolve();
    for (const value of [null, {}, { theme: "light" }, "system", "LIGHT", 1, "<script>"]) {
      store.setTheme(value);
      receivers.forEach((receive) => receive(value));
    }
    expect(store.getSnapshot().theme).toBe("dark");
    expect(ports.write).not.toHaveBeenCalled();
    expect(ports.broadcast).not.toHaveBeenCalled();
    commit("light");
    receivers.forEach((receive) => receive("dark"));
    expect(store.getSnapshot().theme).toBe("light");
    stop();
  });

  it("cleans up listeners even when registration finishes after unmount", async () => {
    const { ports, receivers } = harness();
    let finish: (() => void) | undefined;
    ports.listen = vi.fn((receive) => new Promise<() => void>((resolve) => {
      finish = () => { receivers.add(receive); resolve(() => { receivers.delete(receive); }); };
    }));
    const store = createAppearanceStore(ports);
    const stop = store.subscribe(vi.fn());
    stop();
    finish?.();
    await Promise.resolve();
    expect(receivers.size).toBe(0);
  });

  it("cleans up only after the last subscriber and closes a registration race", async () => {
    const { ports, receivers, commit } = harness("light");
    const store = createAppearanceStore(ports);
    const first = store.subscribe(vi.fn());
    const second = store.subscribe(vi.fn());
    commit("dark");
    await Promise.resolve();
    expect(store.getSnapshot().theme).toBe("dark");
    expect(ports.listen).toHaveBeenCalledTimes(1);
    first();
    expect(receivers.size).toBe(1);
    second();
    expect(receivers.size).toBe(0);
  });

  it("preserves a failed local write when delayed listener registration or events read an old preference", async () => {
    const { ports, receivers } = harness("light");
    let finish: (() => void) | undefined;
    ports.listen = vi.fn((receive) => new Promise<() => void>((resolve) => {
      finish = () => { receivers.add(receive); resolve(() => { receivers.delete(receive); }); };
    }));
    const workingWrite = ports.write;
    ports.write = vi.fn(() => false);
    const store = createAppearanceStore(ports);
    const stop = store.subscribe(vi.fn());
    store.setTheme("dark");
    expect(store.getSnapshot()).toEqual({ theme: "dark", persisted: false });
    finish?.();
    await Promise.resolve();
    receivers.forEach((receive) => receive("light"));
    expect(store.getSnapshot()).toEqual({ theme: "dark", persisted: false });
    expect(ports.apply).toHaveBeenLastCalledWith("dark");
    expect(ports.broadcast).not.toHaveBeenCalled();
    ports.write = workingWrite;
    store.setTheme("light");
    expect(store.getSnapshot()).toEqual({ theme: "light", persisted: true });
    expect(ports.broadcast).toHaveBeenCalledExactlyOnceWith("light");
    stop();
    expect(receivers.size).toBe(0);
  });

  it("keeps the theme usable while reporting a persistence failure", () => {
    const { ports } = harness();
    ports.write = () => false;
    ports.broadcast = vi.fn(async () => { throw new Error("unavailable"); });
    const store = createAppearanceStore(ports);
    store.setTheme("dark");
    expect(store.getSnapshot()).toEqual({ theme: "dark", persisted: false });
    expect(ports.broadcast).not.toHaveBeenCalled();
  });
});
