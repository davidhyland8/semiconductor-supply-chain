// Stage-layered layout: one column per stage in supply order, nodes ordered within
// a column by barycentre sweeps to reduce edge crossings. Edges within a stage
// (e.g. Zeiss -> ASML) push the buyer into a sub-column to the right.

export interface LayoutNode {
  id: string;
  stage: string;
  name?: string;
}

export interface LayoutEdge {
  supplier: string;
  buyer: string;
}

export interface LayoutOptions {
  stageOrder: readonly string[];
  columnGap?: number;
  subColumnGap?: number;
  rowGap?: number;
  sweeps?: number;
}

export type Positions = Record<string, { x: number; y: number }>;

function subColumns(nodes: LayoutNode[], edges: LayoutEdge[]): Map<string, number> {
  const stage = new Map(nodes.map((n) => [n.id, n.stage]));
  const depth = new Map(nodes.map((n) => [n.id, 0]));
  const inner = edges.filter((e) => e.supplier !== e.buyer && stage.get(e.supplier) === stage.get(e.buyer));
  // Longest path within each stage; the iteration cap stops cycles running forever.
  for (let i = 0; i < nodes.length; i++) {
    let changed = false;
    for (const e of inner) {
      const d = (depth.get(e.supplier) ?? 0) + 1;
      if (d > (depth.get(e.buyer) ?? 0) && d <= 3) {
        depth.set(e.buyer, d);
        changed = true;
      }
    }
    if (!changed) break;
  }
  return depth;
}

export function layeredPositions(nodes: LayoutNode[], edges: LayoutEdge[], opts: LayoutOptions): Positions {
  const { stageOrder, columnGap = 260, subColumnGap = 90, rowGap = 56, sweeps = 12 } = opts;
  const column = (n: LayoutNode) => {
    const i = stageOrder.indexOf(n.stage);
    return i === -1 ? stageOrder.length : i;
  };

  const columns: LayoutNode[][] = [];
  for (const n of nodes) (columns[column(n)] ??= []).push(n);
  for (const col of columns) col?.sort((a, b) => (a.name ?? a.id).localeCompare(b.name ?? b.id));

  const neighbours = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) {
    if (e.supplier === e.buyer) continue;
    neighbours.get(e.supplier)?.push(e.buyer);
    neighbours.get(e.buyer)?.push(e.supplier);
  }

  // Relative position (0..1) of each node within its column.
  const rel = new Map<string, number>();
  const assign = (col: LayoutNode[]) =>
    col.forEach((n, i) => rel.set(n.id, col.length === 1 ? 0.5 : i / (col.length - 1)));
  columns.forEach((col) => col && assign(col));

  const reorder = (col: LayoutNode[]) => {
    const key = new Map<string, number>();
    for (const n of col) {
      const ns = neighbours.get(n.id) ?? [];
      key.set(n.id, ns.length ? ns.reduce((s, m) => s + (rel.get(m) ?? 0.5), 0) / ns.length : rel.get(n.id)!);
    }
    // Stable sort, so ties keep the current order and the result is deterministic.
    col.sort((a, b) => key.get(a.id)! - key.get(b.id)!);
    assign(col);
  };

  for (let s = 0; s < sweeps; s++) {
    const order = columns.map((_, i) => i);
    if (s % 2 === 1) order.reverse();
    for (const i of order) if (columns[i]) reorder(columns[i]!);
  }

  const sub = subColumns(nodes, edges);
  const positions: Positions = {};
  columns.forEach((col, c) => {
    col?.forEach((n, i) => {
      positions[n.id] = {
        x: c * columnGap + (sub.get(n.id) ?? 0) * subColumnGap,
        y: (i - (col.length - 1) / 2) * rowGap,
      };
    });
  });
  return positions;
}

export function crossings(positions: Positions, edges: LayoutEdge[]): number {
  let count = 0;
  const segs = edges
    .map((e) => [positions[e.supplier], positions[e.buyer]] as const)
    .filter((s): s is readonly [{ x: number; y: number }, { x: number; y: number }] => !!s[0] && !!s[1]);
  for (let i = 0; i < segs.length; i++) {
    for (let j = i + 1; j < segs.length; j++) {
      const [a, b] = segs[i]!;
      const [c, d] = segs[j]!;
      if (a.x !== c.x || b.x !== d.x) continue; // only compare edges spanning the same columns
      if ((a.y - c.y) * (b.y - d.y) < 0) count++;
    }
  }
  return count;
}
