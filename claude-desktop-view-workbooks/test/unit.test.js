import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import jwt from "jsonwebtoken";
import { searchWorkbooks, hasClearMatch } from "../lib/search.js";
import { getConfig, requireConfig } from "../lib/config.js";
import { createApiAssertion } from "../lib/jwt.js";
import { parseWorkbookRef, buildEmbedUrl } from "../lib/embed-url.js";
import { clearTokenCache, getBearerToken, listWorkbooks, slugFromUrl } from "../lib/sigma.js";

const config = {
  orgSlug: "acme",
  appUrl: "https://app.sigmacomputing.com",
  apiUrl: "https://api.example.com",
  embedClientId: "client-id",
  embedClientSecret: "a-test-secret-value",
  embedUserEmail: "viewer@example.com",
  accountType: "View",
  teams: ["Sales_People"],
  userAttributes: { Store_Region: "West" },
  embedParameters: { hide_menu: "true", theme: "Lite" },
  pageId: "",
  sessionLength: 3600,
  searchAuth: "user",
  apiClientId: "",
  apiClientSecret: "",
  searchPathPrefix: "",
  defaultWorkbookUrl: "",
  debug: false,
};

const workbooks = [
  { name: "Chipotle Food Safety Command Center", slug: "a1", path: "Safety", updatedAt: "2026-10-01", archived: false },
  { name: "Chipotle Food Safety Command Center (Mobile)", slug: "a2", path: "Safety", updatedAt: "2026-10-02", archived: false },
  { name: "Revenue Forecast", slug: "b1", path: "Finance", updatedAt: "2026-09-01", archived: false },
  { name: "Retired Revenue Forecast", slug: "b2", path: "Finance", updatedAt: "2026-10-05", archived: true },
];

test("search matches approximate names and ignores archived workbooks", () => {
  const results = searchWorkbooks(workbooks, "revnue forcast");
  assert.equal(results[0].slug, "b1");
  assert.ok(!results.some((workbook) => workbook.archived));
});

test("search returns several candidates for an ambiguous name", () => {
  const results = searchWorkbooks(workbooks, "chipotle food safety");
  assert.deepEqual(results.map((workbook) => workbook.slug).sort(), ["a1", "a2"]);
  assert.equal(hasClearMatch(results), false);
});

test("search with no query lists the newest workbooks first and honours limit", () => {
  const results = searchWorkbooks(workbooks, "", 2);
  assert.deepEqual(results.map((workbook) => workbook.slug), ["a2", "a1"]);
});

test("a single result counts as a clear match", () => {
  assert.equal(hasClearMatch(searchWorkbooks(workbooks, "revenue forecast")), true);
});

test("parseWorkbookRef takes a slug or a URL and rejects internal IDs", () => {
  assert.deepEqual(parseWorkbookRef({ workbookSlug: "Sales-abc123" }, config), { orgSlug: "acme", slug: "Sales-abc123" });
  assert.deepEqual(
    parseWorkbookRef({ workbookUrl: "https://app.sigmacomputing.com/other/workbook/Sales-abc123?:embed=true" }, config),
    { orgSlug: "other", slug: "Sales-abc123" },
  );
  assert.throws(() => parseWorkbookRef({ workbookSlug: "3f2504e0-4f89-41d3-9a0c-0305e82c3301" }, config), /internal workbook ID/);
  assert.throws(() => parseWorkbookRef({}, config), /Provide a workbookSlug/);
  assert.throws(() => parseWorkbookRef({ workbookUrl: "https://example.com/nope" }, config), /not a Sigma workbook URL/);
});

test("buildEmbedUrl signs a single-use JWT and appends the embed parameters", () => {
  const first = buildEmbedUrl({ orgSlug: "acme", slug: "Sales-abc123" }, config);
  const second = buildEmbedUrl({ orgSlug: "acme", slug: "Sales-abc123" }, config);

  const url = new URL(first);
  assert.equal(url.origin + url.pathname, "https://app.sigmacomputing.com/acme/workbook/Sales-abc123");
  assert.equal(url.searchParams.get(":embed"), "true");
  assert.equal(url.searchParams.get(":hide_menu"), "true");
  assert.equal(url.searchParams.get(":theme"), "Lite");

  const token = url.searchParams.get(":jwt");
  const claims = jwt.verify(token, config.embedClientSecret, { algorithms: ["HS256"] });
  assert.equal(claims.iss, "client-id");
  assert.equal(claims.sub, "viewer@example.com");
  assert.equal(claims.account_type, "View");
  assert.deepEqual(claims.teams, ["Sales_People"]);
  assert.deepEqual(claims.user_attributes, { Store_Region: "West" });
  assert.equal(claims.exp - claims.iat, 3600);
  assert.equal(jwt.decode(token, { complete: true }).header.kid, "client-id");

  const secondClaims = jwt.decode(new URL(second).searchParams.get(":jwt"));
  assert.notEqual(claims.jti, secondClaims.jti);
});

test("buildEmbedUrl can open a specific page", () => {
  const url = new URL(buildEmbedUrl({ orgSlug: "acme", slug: "Sales-abc123" }, { ...config, pageId: "p9" }));
  assert.equal(url.pathname, "/acme/workbook/Sales-abc123/page/p9");
});

test("the API assertion is short-lived and scoped to view", () => {
  const claims = jwt.verify(createApiAssertion(config), config.embedClientSecret, { algorithms: ["HS256"] });
  assert.equal(claims.sub, "viewer@example.com");
  assert.equal(claims.exp - claims.iat, 300);
  assert.deepEqual(claims.embed.permissions, ["view"]);
});

test("getConfig reads the shared and CLAUDE_DESKTOP_ settings", () => {
  const saved = { ...process.env };
  Object.assign(process.env, {
    CLIENT_ID: "cid",
    SECRET: "sec",
    SESSION_LENGTH: "99999999",
    EMAIL: "default@example.com",
    ACCOUNT_TYPE: "View",
    TEAMS: "A, B",
    CLAUDE_DESKTOP_BASE_URL: "https://app.sigmacomputing.com/acme-org/workbook/Home-xyz",
    CLAUDE_DESKTOP_API_URL: "https://aws-api.sigmacomputing.com/v2/",
    CLAUDE_DESKTOP_EMAIL: "override@example.com",
    CLAUDE_DESKTOP_ua_Region: " West ",
    hide_menu: "true",
    CLAUDE_DESKTOP_theme: "Dark",
  });
  try {
    const result = getConfig();
    assert.equal(result.orgSlug, "acme-org");
    assert.equal(result.appUrl, "https://app.sigmacomputing.com");
    assert.equal(result.defaultWorkbookUrl, "https://app.sigmacomputing.com/acme-org/workbook/Home-xyz");
    assert.equal(result.apiUrl, "https://aws-api.sigmacomputing.com");
    assert.equal(result.embedUserEmail, "override@example.com");
    assert.deepEqual(result.teams, ["A", "B"]);
    assert.deepEqual(result.userAttributes, { Region: "West" });
    assert.equal(result.sessionLength, 2592000);
    assert.equal(result.embedParameters.hide_menu, "true");
    assert.equal(result.embedParameters.theme, "Dark");
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
    Object.assign(process.env, saved);
  }
});

test("requireConfig names the .env settings that are missing", () => {
  assert.throws(
    () => requireConfig({ ...config, orgSlug: "", appUrl: "", embedClientId: "" }, ["orgSlug", "appUrl", "embedClientId"]),
    /CLAUDE_DESKTOP_BASE_URL, CLIENT_ID/,
  );
});

test("slugFromUrl returns the last path segment", () => {
  assert.equal(slugFromUrl("https://app.sigmacomputing.com/acme/workbook/Sales-abc123"), "Sales-abc123");
  assert.equal(slugFromUrl("not a url"), "");
});

// --- Sigma API calls, with fetch replaced ---

const realFetch = globalThis.fetch;
let calls;
beforeEach(() => {
  clearTokenCache();
  calls = [];
});
afterEach(() => {
  globalThis.fetch = realFetch;
});

const json = (body, status = 200) => new Response(JSON.stringify(body), { status });

test("the access token is cached and reused", async () => {
  globalThis.fetch = async (url) => {
    calls.push(url);
    return json({ access_token: "tok", expires_in: 3600 });
  };
  assert.equal(await getBearerToken(config), "tok");
  assert.equal(await getBearerToken(config), "tok");
  assert.equal(calls.length, 1);
});

test("a rejected token is refreshed once and the request retried", async () => {
  let tokens = 0;
  let listCalls = 0;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/v2/auth/token")) return json({ access_token: `tok${++tokens}`, expires_in: 3600 });
    listCalls++;
    return listCalls === 1 ? json({ message: "expired" }, 401) : json({ entries: [] });
  };
  const result = await listWorkbooks(config);
  assert.deepEqual(result, { workbooks: [], truncated: false });
  assert.equal(tokens, 2);
});

test("workbooks are collected across pages", async () => {
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/v2/auth/token")) return json({ access_token: "tok", expires_in: 3600 });
    return String(url).includes("page=p2")
      ? json({ entries: [{ name: "Two", url: "https://x/acme/workbook/Two-2" }] })
      : json({ entries: [{ name: "One", url: "https://x/acme/workbook/One-1" }], nextPage: "p2" });
  };
  const { workbooks, truncated } = await listWorkbooks(config);
  assert.deepEqual(workbooks.map((workbook) => workbook.slug), ["One-1", "Two-2"]);
  assert.equal(truncated, false);
});

test("the listing is flagged as truncated after ten pages", async () => {
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/v2/auth/token")) return json({ access_token: "tok", expires_in: 3600 });
    return json({ entries: [], nextPage: "more" });
  };
  assert.equal((await listWorkbooks(config)).truncated, true);
});

test("SEARCH_PATH_PREFIX limits which workbooks are searchable", async () => {
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/v2/auth/token")) return json({ access_token: "tok", expires_in: 3600 });
    return json({
      entries: [
        { name: "In", path: "Shared/Embed", url: "https://x/acme/workbook/In-1" },
        { name: "Out", path: "Private", url: "https://x/acme/workbook/Out-2" },
      ],
    });
  };
  const { workbooks } = await listWorkbooks({ ...config, searchPathPrefix: "Shared" });
  assert.deepEqual(workbooks.map((workbook) => workbook.name), ["In"]);
});

test("a failed sign-in reports Sigma's reason", async () => {
  globalThis.fetch = async () => json({ error_description: "invalid client" }, 400);
  await assert.rejects(getBearerToken(config), /400.*invalid client/);
});

test("missing settings are named in the error", async () => {
  await assert.rejects(getBearerToken({ ...config, embedClientSecret: "" }), /SECRET/);
});

test("nothing writes to stdout, which carries the MCP protocol", () => {
  const files = ["server.js", ...readdirSync(new URL("../lib/", import.meta.url)).map((name) => `lib/${name}`)];
  for (const file of files) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf-8");
    assert.ok(!/console\.log\(|process\.stdout/.test(source), `${file} writes to stdout`);
  }
});
