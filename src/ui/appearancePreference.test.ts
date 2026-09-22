import { afterEach, describe, expect, it, vi } from "vitest";
import { appearanceKey, readAppearance, writeAppearance } from "./appearancePreference";

afterEach(() => vi.restoreAllMocks());

describe("fixed appearance preference", () => {
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
    expect(writeAppearance("dark")).toBe(false);
  });
});
