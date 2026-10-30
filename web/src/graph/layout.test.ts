import { describe, expect, it } from "vitest";
import { crossings, layeredPositions } from "./layout";

const stageOrder = ["up", "mid", "down"];

describe("layeredPositions", () => {
  it("puts each stage in its own column, in supply order", () => {
    const nodes = [
      { id: "d", stage: "down" },
      { id: "u", stage: "up" },
      { id: "m", stage: "mid" },
    ];
    const p = layeredPositions(nodes, [], { stageOrder, columnGap: 100 });
    expect([p.u!.x, p.m!.x, p.d!.x]).toEqual([0, 100, 200]);
  });

  it("shifts a buyer right of a supplier in the same stage", () => {
    const nodes = [
      { id: "zeiss", stage: "up" },
      { id: "asml", stage: "up" },
    ];
    const p = layeredPositions(nodes, [{ supplier: "zeiss", buyer: "asml" }], { stageOrder, columnGap: 100, subColumnGap: 30 });
    expect(p.zeiss!.x).toBe(0);
    expect(p.asml!.x).toBe(30);
  });

  it("survives cycles within a stage", () => {
    const nodes = [
      { id: "a", stage: "up" },
      { id: "b", stage: "up" },
    ];
    const edges = [
      { supplier: "a", buyer: "b" },
      { supplier: "b", buyer: "a" },
    ];
    const p = layeredPositions(nodes, edges, { stageOrder });
    expect(Object.keys(p).sort()).toEqual(["a", "b"]);
  });

  it("orders columns to remove avoidable crossings", () => {
    // Alphabetical order would cross: a1-b2 and a2-b1.
    const nodes = [
      { id: "a1", stage: "up" },
      { id: "a2", stage: "up" },
      { id: "b1", stage: "mid" },
      { id: "b2", stage: "mid" },
    ];
    const edges = [
      { supplier: "a1", buyer: "b2" },
      { supplier: "a2", buyer: "b1" },
    ];
    const p = layeredPositions(nodes, edges, { stageOrder });
    expect(crossings(p, edges)).toBe(0);
  });

  it("is deterministic and centres each column on y = 0", () => {
    const nodes = ["x", "y", "z"].map((id) => ({ id, stage: "mid" }));
    const a = layeredPositions(nodes, [], { stageOrder, rowGap: 10 });
    expect(a).toEqual(layeredPositions(nodes, [], { stageOrder, rowGap: 10 }));
    expect([a.x!.y, a.y!.y, a.z!.y]).toEqual([-10, 0, 10]);
  });
});
