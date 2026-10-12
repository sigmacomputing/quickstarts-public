import { readFile } from "node:fs/promises";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  registerAppResource,
  registerAppTool,
  getUiCapability,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { z } from "zod";
import { getConfig, requireConfig } from "./lib/config.js";
import { listWorkbooks } from "./lib/sigma.js";
import { searchWorkbooks, hasClearMatch } from "./lib/search.js";
import { parseWorkbookRef, buildEmbedUrl } from "./lib/embed-url.js";
import { debug } from "./lib/log.js";

const VIEW_URI = "ui://sigma-workbooks/workbook-view";

const server = new McpServer({ name: "sigma-workbooks", version: "1.0.0" });

const text = (message) => ({ content: [{ type: "text", text: message }] });
const failure = (error) => ({
  isError: true,
  content: [{ type: "text", text: error.message }],
});

server.registerTool(
  "search_workbooks",
  {
    title: "Search Sigma workbooks",
    description:
      "Find Sigma workbooks by name. Matching is fuzzy, so partial or approximate names work. " +
      "Returns each workbook's name, slug, url, path and last-updated date. If clearMatch is true, " +
      "call show_sigma_workbook with that workbook's slug. Otherwise show the user the matches and ask which one they want.",
    inputSchema: {
      query: z.string().optional().describe("Part of the workbook name. Omit to list the most recently updated workbooks."),
      limit: z.number().int().min(1).max(50).optional().describe("Maximum results to return (default 20)."),
    },
    annotations: { readOnlyHint: true },
  },
  async ({ query, limit }) => {
    try {
      const config = getConfig();
      const { workbooks, truncated } = await listWorkbooks(config);
      const results = searchWorkbooks(workbooks, query, limit ?? 20);
      debug(config, `search "${query ?? ""}" matched ${results.length} of ${workbooks.length}`);
      return text(
        JSON.stringify(
          { clearMatch: Boolean(query) && hasClearMatch(results), truncated, results },
          null,
          2,
        ),
      );
    } catch (error) {
      return failure(error);
    }
  },
);

const startupConfig = getConfig();
const paneMode = startupConfig.display === "pane";

const SHOW_DESCRIPTION =
  "Open a Sigma workbook as a live, interactive view. Pass the slug or url returned by search_workbooks. " +
  "Never pass an internal workbook ID. Each call creates a single-use link, so call it again for a fresh one instead of reusing a link.";

const SHOW_PANE_DESCRIPTION =
  "Open a Sigma workbook in Claude's built-in browser pane. Pass the slug or url returned by search_workbooks. " +
  "Never pass an internal workbook ID. This tool returns a single-use sign-in URL. After calling it, use the built-in " +
  "browser to open that URL, and do not repeat the URL in your reply, because it contains a sign-in token. " +
  "Each call creates a new link, so call it again for a fresh one instead of reusing a link.";

async function showWorkbook({ workbookSlug, workbookUrl }) {
  try {
    const config = getConfig();
    requireConfig(config, ["orgSlug", "embedClientId", "embedClientSecret", "embedUserEmail"]);
    const ref = parseWorkbookRef(
      { workbookSlug, workbookUrl: workbookUrl || (workbookSlug ? "" : config.defaultWorkbookUrl) },
      config,
    );
    const embedUrl = buildEmbedUrl(ref, config);
    debug(config, `opening ${ref.slug}`);

    const uiSupport = getUiCapability(server.server.getClientCapabilities());
    const hostCanShowInline = Boolean(uiSupport?.mimeTypes?.includes(RESOURCE_MIME_TYPE));
    const inline = config.display === "inline" || (config.display === "auto" && hostCanShowInline);

    if (inline) {
      return {
        content: [
          {
            type: "text",
            text: "The workbook is displayed inline. Do not open the link anywhere else, because it works only once.",
          },
        ],
        structuredContent: { embedUrl },
      };
    }
    return text(
      "Use the built-in browser to open this URL in the browser pane now. It works only once, so do not load it a " +
        "second time, and do not repeat it in your reply because it contains a sign-in token. " +
        embedUrl,
    );
  } catch (error) {
    return failure(error);
  }
}

const showInputSchema = {
  workbookSlug: z.string().optional().describe("The last segment of the workbook URL."),
  workbookUrl: z.string().optional().describe("The full workbook URL."),
};

// In pane mode the tool carries no inline view. Otherwise Claude believes the
// workbook is already displayed and never opens the browser pane.
if (paneMode) {
  server.registerTool(
    "show_sigma_workbook",
    { title: "Show a Sigma workbook", description: SHOW_PANE_DESCRIPTION, inputSchema: showInputSchema },
    showWorkbook,
  );
} else {
  registerAppTool(
    server,
    "show_sigma_workbook",
    {
      title: "Show a Sigma workbook",
      description: SHOW_DESCRIPTION,
      inputSchema: showInputSchema,
      _meta: { ui: { resourceUri: VIEW_URI } },
    },
    showWorkbook,
  );
}

// The view frames Sigma, so the host's content security policy must allow it.
// It is declared on the resource listing and on the content, because hosts may
// read either.
function viewMeta() {
  const { appUrl } = getConfig();
  const origins = appUrl ? [appUrl] : [];
  return {
    ui: {
      csp: { frameDomains: origins, connectDomains: origins, resourceDomains: origins },
      prefersBorder: false,
    },
  };
}

registerAppResource(
  server,
  "Sigma workbook view",
  VIEW_URI,
  { description: "Shows a Sigma workbook in an iframe.", _meta: viewMeta() },
  async () => ({
    contents: [
      {
        uri: VIEW_URI,
        mimeType: RESOURCE_MIME_TYPE,
        text: await readFile(new URL("./view/workbook-view.html", import.meta.url), "utf-8"),
        _meta: viewMeta(),
      },
    ],
  }),
);

process.on("unhandledRejection", (error) => console.error("[sigma-workbooks]", error));

await server.connect(new StdioServerTransport());
debug(getConfig(), "server ready");
