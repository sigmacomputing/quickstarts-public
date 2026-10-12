// stdout carries the MCP protocol, so every log line goes to stderr.
export function debug(config, ...args) {
  if (config.debug) console.error("[sigma-workbooks]", ...args);
}
