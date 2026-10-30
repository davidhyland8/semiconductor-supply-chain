import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const BUILD_DIR = fileURLToPath(new URL("../data/build/", import.meta.url));

// Only the latest graph version is bundled. Restart the dev server after `scg build`.
function latestGraph(): string {
  const versions = readdirSync(BUILD_DIR)
    .map((f) => /^graph\.v(\d+)\.json$/.exec(f))
    .filter((m): m is RegExpExecArray => m !== null)
    .sort((a, b) => Number(a[1]) - Number(b[1]));
  const latest = versions.pop();
  if (!latest) throw new Error("No graph build in data/build. Run `uv run scg build`.");
  return BUILD_DIR + latest[0];
}

export default defineConfig({
  base: "./",
  resolve: { alias: [{ find: /^@graph(\?.*)?$/, replacement: `${latestGraph()}$1` }] },
  // The graph builds live in ../data/build, outside the web root.
  server: { fs: { allow: [fileURLToPath(new URL("..", import.meta.url))] } },
});
