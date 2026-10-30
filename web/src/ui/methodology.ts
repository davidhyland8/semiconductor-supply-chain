// The methodology page: docs/methodology.md, rendered from the repo at build time.

import { marked } from "marked";
import methodology from "../../../docs/methodology.md?raw";

let rendered: string | null = null;

export function methodologyHtml(): string {
  // The Markdown is this repository's own document, not user or third-party input.
  rendered ??= marked.parse(methodology, { async: false });
  return `<article class="doc">${rendered}</article>`;
}
