import { describe, expect, it } from "vitest";
import vectors from "../../tests/fixtures/capability_ref_vectors.json";
import {
  displayedHealth,
  effectiveHealth,
  isWeeklyWindow,
  providerName,
  windowFamily,
  windowMetric,
  type Capability,
} from "./quotaPresentation";

describe("shared capability_ref golden vectors", () => {
  it("matches Python projection encoding across all supported and bridged providers", () => {
    const accountHash = "a".repeat(24);
    const rowHash = "b".repeat(24);
    const projectedRows: Capability[] = vectors.map((vector) => {
      const modelMatch = vector.source_ref.match(
        /^cap-(?:minimax-(?:cn|global)|antigravity)-model-(\d+)-(5h|weekly)$/u,
      );
      let projectedRef: string;
      if (modelMatch) {
        projectedRef = `cap-${vector.provider_id}-row-${rowHash}-account-${accountHash}-model-${modelMatch[1]}-${modelMatch[2]}`;
      } else if (vector.display_kind === "window") {
        const period = vector.source_ref.endsWith("-5h")
          ? "-5h"
          : vector.source_ref.endsWith("-weekly")
            ? "-weekly"
            : "";
        projectedRef = `cap-${vector.provider_id}-row-${rowHash}-account-${accountHash}${period}`;
      } else {
        projectedRef = `cap-${vector.provider_id}-account-${rowHash}`;
      }
      const row: Capability = {
        capability_ref: projectedRef,
        display_kind: vector.display_kind,
        health: "ok",
        value_display: vector.value_display,
      };
      expect(providerName(row.capability_ref)).toBe(vector.expected_provider_name);
      expect(isWeeklyWindow(row)).toBe(vector.expected_is_weekly);
      expect(windowMetric(row.value_display)).toEqual(vector.expected_window_metric);
      return row;
    });

    const exhaustedFamilies = new Set(
      projectedRows
        .filter((row) => isWeeklyWindow(row) && displayedHealth(row) === "exhausted")
        .map(windowFamily),
    );
    const antigravity5h = projectedRows.find((row) =>
      row.capability_ref.startsWith("cap-antigravity-") && row.capability_ref.endsWith("-5h"),
    )!;
    expect(effectiveHealth(antigravity5h, exhaustedFamilies)).toBe("unavailable");
  });
});
