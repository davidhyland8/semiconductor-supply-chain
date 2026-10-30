const ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]!);

// Only http(s) links from the data are rendered as links.
export const safeUrl = (u: string | undefined) => (u && /^https?:\/\//.test(u) ? u : "");

export const pct = (x: number) => `${(x * 100).toFixed(x < 0.1 ? 1 : 0)}%`;
