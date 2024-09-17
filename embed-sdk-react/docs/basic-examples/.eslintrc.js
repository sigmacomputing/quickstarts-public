/** @type {import("eslint").Linter.Config} */
module.exports = {
  root: true,
  extends: ["@sigmacomputing/eslint-config/next.js"],
  parser: "@typescript-eslint/parser",
  parserOptions: {
    project: true,
  },
  ignorePatterns: ["next.config.mjs"],
};
