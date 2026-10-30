import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  // The graph builds live in ../data/build, outside the web root.
  server: { fs: { allow: [fileURLToPath(new URL("..", import.meta.url))] } },
});
