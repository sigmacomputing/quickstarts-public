import { defineConfig } from "tsup";

export default defineConfig({
  entry: {
    index: "src/index.ts",
  },
  sourcemap: false,
  minify: false,
  dts: true,
  clean: true,
  format: ["esm", "cjs"],
  loader: {
    ".js": "jsx",
  },
});
