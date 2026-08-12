import catalogDocument from "../agent_quota/resources/provider_catalog_v1.json";

export type CatalogStatus = "supported" | "experimental" | "catalog-only" | "unsupported";

export type ProviderCatalogRow = {
  adapter_ids: string[];
  blocker: string;
  canonical_id: string;
  confidence: string;
  row_id: string;
  screenshot_label: string;
  support_tier: "Supported" | "Experimental" | "Catalog-only" | "Unsupported";
  wallet: { evidence: string; endpoint: string; status: CatalogStatus };
  window: { evidence: string; endpoint: string; status: CatalogStatus };
};

type ProviderCatalogDocument = {
  rows: ProviderCatalogRow[];
  schema_version: string;
  stats: { rows: number; unique_row_id: number };
};

export const providerCatalog = catalogDocument as ProviderCatalogDocument;

const visibleAdapterIds = new Set([
  "deepseek",
  "glm-cn",
  "kimi-cn",
  "kimi-code",
  "minimax-cn",
]);

if (
  providerCatalog.rows.length !== 78 ||
  new Set(providerCatalog.rows.map((row) => row.row_id)).size !== 78
) {
  throw new Error("provider catalog integrity mismatch");
}

export const visibleProviderRows = providerCatalog.rows.filter((row) =>
  row.adapter_ids.some((adapterId) => visibleAdapterIds.has(adapterId)),
);

if (visibleProviderRows.length !== 5) {
  throw new Error("visible provider preset integrity mismatch");
}
