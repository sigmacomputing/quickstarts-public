import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const entries = [
  { name: "Chipotle Food Safety Command Center", url: "https://app.sigmacomputing.com/acme/workbook/Chipotle-Food-Safety-aaa111", path: "Safety", updatedAt: "2026-10-01" },
  { name: "Revenue Forecast", url: "https://app.sigmacomputing.com/acme/workbook/Revenue-Forecast-bbb222", path: "Finance", updatedAt: "2026-09-01" },
];

let api;
let apiUrl;
let tokenRequests = 0;

before(async () => {
  api = http.createServer((req, res) => {
    res.setHeader("Content-Type", "application/json");
    if (req.method === "POST" && req.url === "/v2/auth/token") {
      tokenRequests++;
      return res.end(JSON.stringify({ access_token: "fake-token", expires_in: 3600 }));
    }
    if (req.url.startsWith("/v2/workbooks") && req.headers.authorization === "Bearer fake-token") {
      return res.end(JSON.stringify({ entries }));
    }
    res.statusCode = 401;
    res.end(JSON.stringify({ message: "unauthorized" }));
  });
  await new Promise((resolve) => api.listen(0, "127.0.0.1", resolve));
  apiUrl = `http://127.0.0.1:${api.address().port}`;
});

after(() => api.close());

// Every setting is set explicitly, including blanks, so a real .env cannot change the result.
const BLANK_SETTINGS = [
  "ACCOUNT_TYPE", "TEAMS", "SESSION_LENGTH", "DEBUG", "page_id",
  "disable_auto_refresh", "disable_mobile_view", "hide_folder_navigation", "hide_menu",
  "hide_page_controls", "hide_reload_button", "hide_title", "hide_tooltip",
  "hide_view_select", "lng", "menu_position", "responsive_height", "theme", "view_id",
  "CLAUDE_DESKTOP_EMAIL", "CLAUDE_DESKTOP_ACCOUNT_TYPE", "CLAUDE_DESKTOP_TEAMS",
  "CLAUDE_DESKTOP_SEARCH_PATH_PREFIX", "CLAUDE_DESKTOP_SEARCH_AUTH",
  "CLAUDE_DESKTOP_API_CLIENT_ID", "CLAUDE_DESKTOP_API_CLIENT_SECRET",
];

const serverEnv = () => ({
  ...Object.fromEntries(BLANK_SETTINGS.map((name) => [name, ""])),
  CLIENT_ID: "client-id",
  SECRET: "a-test-secret-value",
  EMAIL: "viewer@example.com",
  CLAUDE_DESKTOP_BASE_URL: "https://app.sigmacomputing.com/acme/workbook/Home-000",
  CLAUDE_DESKTOP_API_URL: apiUrl,
});

async function connect(capabilities = {}) {
  const client = new Client({ name: "test-client", version: "1.0.0" }, { capabilities });
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ["server.js"],
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    env: serverEnv(),
    stderr: "ignore",
  });
  await client.connect(transport);
  return client;
}

test("lists both tools and the view resource", async () => {
  const client = await connect();
  try {
    const { tools } = await client.listTools();
    assert.deepEqual(tools.map((tool) => tool.name).sort(), ["search_workbooks", "show_sigma_workbook"]);
    const show = tools.find((tool) => tool.name === "show_sigma_workbook");
    assert.equal(show._meta.ui.resourceUri, "ui://sigma-workbooks/workbook-view");

    const { resources } = await client.listResources();
    assert.ok(resources.some((resource) => resource.uri === "ui://sigma-workbooks/workbook-view"));
    const view = await client.readResource({ uri: "ui://sigma-workbooks/workbook-view" });
    assert.equal(view.contents[0].mimeType, "text/html;profile=mcp-app");
    assert.match(view.contents[0].text, /ui\/initialize/);
    assert.deepEqual(view.contents[0]._meta.ui.csp.frameDomains, ["https://app.sigmacomputing.com"]);
  } finally {
    await client.close();
  }
});

test("search finds a workbook by approximate name", async () => {
  const client = await connect();
  try {
    const result = await client.callTool({ name: "search_workbooks", arguments: { query: "chipotle safty" } });
    const body = JSON.parse(result.content[0].text);
    assert.equal(body.results[0].slug, "Chipotle-Food-Safety-aaa111");
    assert.equal(body.clearMatch, true);

    await client.callTool({ name: "search_workbooks", arguments: { query: "revenue" } });
    assert.equal(tokenRequests, 1, "the access token is reused across searches");
  } finally {
    await client.close();
  }
});

test("a host without MCP Apps gets a single-use URL to open in the browser pane", async () => {
  const client = await connect();
  try {
    const result = await client.callTool({ name: "show_sigma_workbook", arguments: { workbookSlug: "Revenue-Forecast-bbb222" } });
    assert.ok(!result.isError);
    assert.match(result.content[0].text, /browser pane/);
    assert.match(result.content[0].text, /\/acme\/workbook\/Revenue-Forecast-bbb222\?:embed=true&:jwt=/);
    assert.equal(result.structuredContent, undefined);
  } finally {
    await client.close();
  }
});

test("a host with MCP Apps gets the URL as structured content for the inline view", async () => {
  const client = await connect({
    extensions: { "io.modelcontextprotocol/ui": { mimeTypes: ["text/html;profile=mcp-app"] } },
  });
  try {
    const result = await client.callTool({ name: "show_sigma_workbook", arguments: { workbookSlug: "Revenue-Forecast-bbb222" } });
    assert.ok(!result.isError);
    assert.match(result.content[0].text, /displayed inline/);
    assert.match(result.structuredContent.embedUrl, /:jwt=/);
  } finally {
    await client.close();
  }
});

test("an internal workbook ID returns a helpful error", async () => {
  const client = await connect();
  try {
    const result = await client.callTool({
      name: "show_sigma_workbook",
      arguments: { workbookSlug: "3f2504e0-4f89-41d3-9a0c-0305e82c3301" },
    });
    assert.equal(result.isError, true);
    assert.match(result.content[0].text, /internal workbook ID/);
  } finally {
    await client.close();
  }
});
