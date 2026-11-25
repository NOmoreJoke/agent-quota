import { afterEach, describe, expect, it, vi } from "vitest";
import {
  appearanceKey,
  motionKey,
  readAppearance,
  readMotionPreference,
  writeAppearance,
  writeMotionPreference,
} from "./appearancePreference";

afterEach(() => vi.restoreAllMocks());

describe("fixed appearance and motion preferences", () => {
  it("reads only the fixed appearance key and accepts the closed light/dark enum", () => {
    const read = vi.spyOn(Storage.prototype, "getItem");
    for (const value of [null, "system", "Dark", "", '{"theme":"dark"}', "<script>"]) {
      read.mockReturnValue(value);
      expect(readAppearance()).toBeNull();
    }
    for (const value of ["light", "dark"] as const) {
      read.mockReturnValue(value);
      expect(readAppearance()).toBe(value);
    }
    expect(read.mock.calls.every(([key]) => key === appearanceKey)).toBe(true);
  });

  it("reads and writes only the fixed motion key with the closed on/off enum", () => {
    const read = vi.spyOn(Storage.prototype, "getItem");
    const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => undefined);
    for (const value of [null, "true", "ON", "reduce", "", "<script>"]) {
      read.mockReturnValue(value);
      expect(readMotionPreference()).toBeNull();
    }
    for (const value of ["on", "off"] as const) {
      read.mockReturnValue(value);
      expect(readMotionPreference()).toBe(value);
      expect(writeMotionPreference(value)).toBe(true);
    }
    // @ts-expect-error Untrusted runtime input must be rejected despite the TypeScript type.
    expect(writeMotionPreference("auto")).toBe(false);
    expect(read.mock.calls.every(([key]) => key === motionKey)).toBe(true);
    expect(write.mock.calls).toEqual([[motionKey, "on"], [motionKey, "off"]]);
  });

  it("writes only validated appearances to the fixed key", () => {
    const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => undefined);
    expect(writeAppearance("light")).toBe(true);
    expect(writeAppearance("dark")).toBe(true);
    // @ts-expect-error Untrusted runtime input must be rejected despite the TypeScript type.
    expect(writeAppearance("system")).toBe(false);
    expect(write.mock.calls).toEqual([[appearanceKey, "light"], [appearanceKey, "dark"]]);
  });

  it("handles unavailable or full storage without interrupting the application", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("unavailable"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
    expect(readAppearance()).toBeNull();
    expect(readMotionPreference()).toBeNull();
    expect(writeAppearance("dark")).toBe(false);
    expect(writeMotionPreference("off")).toBe(false);
  });
});
