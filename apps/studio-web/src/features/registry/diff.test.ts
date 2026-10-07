/** PAR-07 — ingredient/process diff renders added/removed/changed
 * honestly; reordering is a change, missing fields stay "—". */

import { describe, expect, it } from "vitest";

import {
  ingredientDiff,
  metaDiff,
  parseIngredients,
  processStepDiff,
} from "./diff";

const BASE = {
  ingredients: [
    {
      name: "water",
      materialId: "m-water",
      amount: { value: "70", unit: "mass_percent" },
      role: "solvent",
    },
    {
      name: "resin",
      materialId: "m-resin",
      amount: { value: "20", unit: "mass_percent" },
      role: "binder",
    },
    {
      name: "additive",
      materialId: "m-add",
      amount: { value: "10", unit: "mass_percent" },
      role: "additive",
    },
  ],
  declaredTotal: "100",
  amountBasis: "mass_percent",
  completeness: "complete",
};

describe("ingredientDiff", () => {
  it("reports added/removed/changed/unchanged by ingredient identity", () => {
    const next = {
      ingredients: [
        {
          name: "water",
          materialId: "m-water",
          amount: { value: "65", unit: "mass_percent" },
          role: "solvent",
        },
        {
          name: "resin",
          materialId: "m-resin",
          amount: { value: "20", unit: "mass_percent" },
          role: "binder",
        },
        {
          name: "coalescent",
          materialId: "m-coal",
          amount: { value: "5", unit: "mass_percent" },
          role: "co-solvent",
        },
      ],
    };
    const rows = ingredientDiff(BASE, next);
    const byKey = new Map(rows.map((r) => [r.key, r]));
    expect(byKey.get("m-water")?.status).toBe("changed");
    expect(byKey.get("m-water")?.changes).toContain("value: 70 → 65");
    expect(byKey.get("m-resin")?.status).toBe("unchanged");
    expect(byKey.get("m-add")?.status).toBe("removed");
    expect(byKey.get("m-coal")?.status).toBe("added");
  });

  it("keys by materialId before alias/name", () => {
    const rows = ingredientDiff(
      { ingredients: [{ materialId: "x", name: "old name" }] },
      { ingredients: [{ materialId: "x", name: "new name" }] },
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].status).toBe("unchanged");
  });

  it("non-list payloads parse to empty", () => {
    expect(parseIngredients(null)).toEqual([]);
    expect(ingredientDiff({}, BASE)).toHaveLength(3);
    expect(ingredientDiff({}, BASE).every((r) => r.status === "added")).toBe(
      true,
    );
    expect(ingredientDiff(BASE, {}).every((r) => r.status === "removed")).toBe(
      true,
    );
  });
});

describe("metaDiff", () => {
  it("marks changed meta fields only", () => {
    const rows = metaDiff(BASE, { ...BASE, declaredTotal: "105" });
    const total = rows.find((r) => r.field === "declared total");
    expect(total?.changed).toBe(true);
    expect(total?.left).toBe("100");
    expect(total?.right).toBe("105");
    expect(rows.find((r) => r.field === "amount basis")?.changed).toBe(false);
  });
});

describe("processStepDiff", () => {
  const left = {
    steps: [
      { order: 1, action: "charge" },
      { order: 2, action: "mix", duration: "30m" },
      { order: 3, action: "filter" },
    ],
  };

  it("reordered steps are changes, not a silent no-op", () => {
    const right = {
      steps: [
        { order: 1, action: "mix", duration: "30m" },
        { order: 2, action: "charge" },
        { order: 3, action: "filter" },
      ],
    };
    const rows = processStepDiff(left, right);
    expect(rows.filter((r) => r.status === "changed")).toHaveLength(2);
  });

  it("added and removed steps surface", () => {
    const right = {
      steps: [
        { order: 1, action: "charge" },
        { order: 2, action: "mix", duration: "30m" },
        { order: 3, action: "filter" },
        { order: 4, action: "discharge" },
      ],
    };
    const rows = processStepDiff(left, right);
    expect(rows[3].status).toBe("added");
    expect(processStepDiff(right, left)[3].status).toBe("removed");
  });
});
