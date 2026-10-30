import { expect, it } from "vitest";
import { countryName, explainCause } from "./labels";
import type { Rule } from "./scenario/types";

const name = (id: string) => id.toUpperCase();
const input = (id: string) => `${id} tools`;

it("explains every scenario rule in words", () => {
  const rules: Rule[] = [
    "company_offline",
    "stage_offline",
    "country_offline",
    "country_offline_hq_fallback",
    "country_partial",
    "all_suppliers_lost",
    "alternatives_unrecorded",
    "sole_source",
    "weight_threshold",
    "some_suppliers_lost",
    "degraded_supplier",
  ];
  for (const rule of rules) {
    const text = explainCause({ rule, stage: "equipment", countries: ["JP"], input: "euv", lost: ["asml"], degraded: ["tel"] }, name, input);
    expect(text, rule).toMatch(/\.$/);
  }
  expect(explainCause({ rule: "sole_source", input: "euv", lost: ["asml"] }, name, input)).toBe(
    "Lost a sole-source supplier of euv tools: ASML.",
  );
  expect(explainCause({ rule: "country_partial", countries: ["JP", "TW"] }, name, input)).toBe(
    "Some of its recorded production is in Japan, Taiwan.",
  );
});

it("names countries, including the EU bucket", () => {
  expect(countryName("NL")).toBe("Netherlands");
  expect(countryName("EU")).toBe("European Union");
});
