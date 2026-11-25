import { describe, expect, it } from "vitest";
import { filterProducts, launchProducts, productStatus } from "./launchProducts";
import { providerFromAccount, providerName, windowMetric } from "./quotaPresentation";

describe("approved launch products", () => {
  it("preserves nine candidates, seven executable products including WorkBuddy CN, and six information cards", () => {
    expect(launchProducts).toHaveLength(15);
    expect(new Set(launchProducts.map((p) => p.brand)).size).toBe(10);
    expect(launchProducts.filter((p) => p.candidate)).toHaveLength(9);
    expect(launchProducts.filter((p) => p.creatable).map((p) => p.adapter_id).sort()).toEqual([
      "antigravity", "deepseek", "glm-cn", "kimi-cn", "kimi-code", "minimax-cn", "workbuddy-cn",
    ]);
    expect(launchProducts.filter((p) => !p.candidate)).toHaveLength(6);
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
    expect(providerName("cap-workbuddy-cn-row")).toBe("WorkBuddy");
    expect(providerName("cap-qoder-personal")).toBe("Qoder");
    expect(providerFromAccount("WorkBuddy 个人版（中国区）")).toBe("WorkBuddy");
    expect(windowMetric("周期积分 (750 / 1000) · 剩余 75%")).toEqual({ mode: "remaining", percentage: 75 });
  });
});
