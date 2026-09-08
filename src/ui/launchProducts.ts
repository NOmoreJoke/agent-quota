import document from "../agent_quota/resources/launch_products_v1.json";

export type LaunchProduct = typeof document.products[number];
export const launchProducts: readonly LaunchProduct[] = document.products;

export function filterProducts(query: string, mode: "all" | "window" | "wallet"): readonly LaunchProduct[] {
  const normalized = query.trim().toLowerCase();
  return launchProducts.filter((product) =>
    (!normalized || `${product.display_name} ${product.brand} ${product.product_id}`.toLowerCase().includes(normalized))
    && (mode === "all" || product[mode]),
  );
}

export function productStatus(product: LaunchProduct): string {
  if (product.creatable) return "可添加 · 实机验收待完成";
  return product.candidate ? "接入待完成 · 暂不可添加" : "信息展示 · 暂无已核验查询接口";
}
