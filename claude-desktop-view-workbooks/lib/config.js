import { config as loadEnv } from "dotenv";
import { fileURLToPath } from "node:url";

// Claude Desktop starts this server from an unknown working directory, so the
// .env path is resolved relative to this file. `quiet` stops dotenv writing to
// stdout, which is reserved for the MCP protocol.
loadEnv({
  path: fileURLToPath(new URL("../.env", import.meta.url)),
  quiet: true,
});

// Settings that start with this prefix apply only to this project and
// override the shared defaults, as in the other embedding QuickStarts.
const MODE = "CLAUDE_DESKTOP";

const EMBED_PARAMETERS = [
  "disable_auto_refresh",
  "disable_mobile_view",
  "hide_folder_navigation",
  "hide_menu",
  "hide_page_controls",
  "hide_reload_button",
  "hide_title",
  "hide_tooltip",
  "hide_view_select",
  "lng",
  "menu_position",
  "responsive_height",
  "theme",
  "view_id",
];

export function getConfig() {
  const env = process.env;
  const pick = (name) => env[`${MODE}_${name}`] || env[name] || "";

  // The org and app host come from one workbook URL, as in the other QuickStarts.
  const baseUrl = env[`${MODE}_BASE_URL`] || "";
  let appUrl = "";
  let orgSlug = "";
  try {
    const url = new URL(baseUrl);
    appUrl = url.origin;
    orgSlug = url.pathname.split("/").filter(Boolean)[0] || "";
  } catch {
    // Reported by requireConfig when a tool needs it.
  }

  const userAttributes = {};
  for (const [key, value] of Object.entries(env)) {
    if (key.startsWith(`${MODE}_ua_`) && value) {
      userAttributes[key.slice(`${MODE}_ua_`.length)] = value.trim();
    }
  }

  const embedParameters = {};
  for (const name of EMBED_PARAMETERS) {
    const value = pick(name);
    if (value) embedParameters[name] = value;
  }

  return {
    orgSlug,
    appUrl,
    defaultWorkbookUrl: baseUrl.includes("/workbook/") ? baseUrl : "",
    apiUrl: (env[`${MODE}_API_URL`] || "").replace(/\/+$/, "").replace(/\/v2$/, ""),
    embedClientId: env.CLIENT_ID,
    embedClientSecret: env.SECRET,
    embedUserEmail: pick("EMAIL"),
    accountType: pick("ACCOUNT_TYPE"),
    teams: pick("TEAMS").split(",").map((team) => team.trim()).filter(Boolean),
    userAttributes,
    embedParameters,
    pageId: pick("page_id"),
    display: ["inline", "auto"].includes(env[`${MODE}_DISPLAY`]) ? env[`${MODE}_DISPLAY`] : "pane",
    sessionLength: Math.min(parseInt(env.SESSION_LENGTH) || 3600, 2592000),
    searchPathPrefix: env[`${MODE}_SEARCH_PATH_PREFIX`] || "",
    debug: env.DEBUG === "true",
  };
}

const ENV_NAMES = {
  orgSlug: `${MODE}_BASE_URL`,
  appUrl: `${MODE}_BASE_URL`,
  apiUrl: `${MODE}_API_URL`,
  embedClientId: "CLIENT_ID",
  embedClientSecret: "SECRET",
  embedUserEmail: "EMAIL",
};

// Fails with the names of the missing .env settings so Claude can relay them.
export function requireConfig(config, keys) {
  const missing = [
    ...new Set(keys.filter((key) => !config[key]).map((key) => ENV_NAMES[key])),
  ];
  if (missing.length) {
    throw new Error(
      `Missing settings in the .env file: ${missing.join(", ")}. See .env.example.`,
    );
  }
}
