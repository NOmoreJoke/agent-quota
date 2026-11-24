import { describe, expect, it } from "vitest";
import { filterProducts, launchProducts, productStatus } from "./launchProducts";

describe("approved launch products", () => {
  it("preserves eight candidates, six executable products including Antigravity OAuth, and five information cards", () => {
    expect(launchProducts).toHaveLength(13);
    expect(new Set(launchProducts.map((p) => p.brand)).size).toBe(8);
    expect(launchProducts.filter((p) => p.candidate)).toHaveLength(8);
    expect(launchProducts.filter((p) => p.creatable).map((p) => p.adapter_id).sort()).toEqual([
      "antigravity", "deepseek", "glm-cn", "kimi-cn", "kimi-code", "minimax-cn",
    ]);
    expect(launchProducts.filter((p) => !p.candidate)).toHaveLength(5);
    for (const product of launchProducts.filter((p) => !p.candidate)) {
      expect(product.adapter_id).toBeNull();
      expect(product.creatable).toBe(false);
      expect(productStatus(product)).toContain("信息展示");
    }
    for (const product of launchProducts.filter((p) => p.candidate && !p.creatable)) {
      expect(productStatus(product)).toContain("接入待完成");
    }
  });

  it("filters product capabilities without claiming unsupported MiMo windows", () => {
    expect(filterProducts("  KIMI  ", "all")).toHaveLength(2);
    expect(filterProducts("MiMo", "window")).toHaveLength(0);
    expect(filterProducts("火山", "wallet").map((p) => p.adapter_id)).toEqual(["volc-wallet"]);
    expect(filterProducts("百炼", "window")).toHaveLength(2);
  });
});
