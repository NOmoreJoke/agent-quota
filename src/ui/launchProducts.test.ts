import { describe, expect, it } from "vitest";
import { filterProducts, launchProducts, productStatus } from "./launchProducts";

describe("approved launch products", () => {
  it("preserves eight candidates, five executable products, Antigravity bridge, and three information cards", () => {
    expect(launchProducts).toHaveLength(11);
    expect(new Set(launchProducts.map((p) => p.brand)).size).toBe(8);
    expect(launchProducts.filter((p) => p.candidate)).toHaveLength(8);
    expect(launchProducts.filter((p) => p.creatable).map((p) => p.adapter_id).sort()).toEqual([
      "deepseek", "glm-cn", "kimi-cn", "kimi-code", "minimax-cn",
    ]);
    for (const product of launchProducts.filter((p) => !p.candidate)) {
      expect(product.adapter_id).toBeNull();
      expect(product.creatable).toBe(false);
      expect(productStatus(product)).toContain("信息展示");
    }
    for (const product of launchProducts.filter((p) => p.candidate && !p.creatable)) {
      if (product.adapter_id === "antigravity") {
        expect(productStatus(product)).toContain("statusLine");
      } else {
        expect(productStatus(product)).toContain("接入待完成");
      }
    }
  });

  it("filters product capabilities without claiming unsupported MiMo windows", () => {
    expect(filterProducts("  KIMI  ", "all")).toHaveLength(2);
    expect(filterProducts("MiMo", "window")).toHaveLength(0);
    expect(filterProducts("火山", "wallet").map((p) => p.adapter_id)).toEqual(["volc-wallet"]);
    expect(filterProducts("百炼", "window")).toHaveLength(2);
  });
});
