// helpers/config.js
require("dotenv").config();

/**
 * Parse an environment variable as a boolean.
 */
function parseBoolean(value) {
  return String(value).toLowerCase() === "true";
}

module.exports = {
  // Auth
  email: process.env.EMAIL,
  clientId: process.env.CLIENT_ID,
  secret: process.env.SECRET,
  sessionLength: parseInt(process.env.SESSION_LENGTH, 10) || 3600,

  // Sigma API base (for provisioning, impersonation)
  apiBaseUrl: process.env.API_BASE_URL || "https://aws-api.sigmacomputing.com/v2",
  authUrl: process.env.AUTH_URL || "https://aws-api.sigmacomputing.com/v2/auth/token",

  // Default account type (can be overridden per request)
  accountType: process.env.ACCOUNT_TYPE || "view",

  // Embed URL for the Sigma app
  embedUrlWorkbook: process.env.EMBED_URL_WORKBOOK,
  embedUrlPage: process.env.EMBED_URL_PAGE,
  embedUrlElement: process.env.EMBED_URL_ELEMENT,

  // Embed users – one-time provisioning input
  viewEmail: process.env.VIEW_EMAIL,
  buildEmail: process.env.BUILD_EMAIL,

  // Role-to-memberId mapping used during embed generation
  memberIds: {
    admin: process.env.ADMIN_MEMBER_ID,
    build: process.env.BUILD_MEMBER_ID,
    view: process.env.VIEW_MEMBER_ID,
  },

  // Embed team membership for JWT payload
  teams: process.env.TEAMS?.split(",").map(t => t.trim()).filter(Boolean) || [],

  // Full URL to the target element
  defaultWorkbookId: process.env.GETTING_STARTED_BASE_URL || process.env.WORKBOOK_ID || null,

  // UI iframe options (for query param–based embedding)
  embedUiOptions: {
    disable_auto_refresh: parseBoolean(process.env.disable_auto_refresh),
    disable_mobile_view: parseBoolean(process.env.disable_mobile_view),
    hide_folder_navigation: parseBoolean(process.env.hide_folder_navigation),
    hide_menu: parseBoolean(process.env.hide_menu),
    hide_page_controls: parseBoolean(process.env.hide_page_controls),
    hide_reload_button: parseBoolean(process.env.hide_reload_button),
    hide_title: parseBoolean(process.env.hide_title),
    hide_tooltip: parseBoolean(process.env.hide_tooltip),
    hide_view_select: parseBoolean(process.env.hide_view_select),
    responsive_height: parseBoolean(process.env.responsive_height),
    lng: process.env.lng || "English",
    menu_position: process.env.menu_position || "bottom",
    theme: process.env.theme || "Lite",
    page_id: process.env.page_id || "",
    view_id: process.env.view_id || "",
  },
};

// Optional debug logging
if (process.env.DEBUG === "true") {
  console.log("Loaded config:");
  console.log("  CLIENT_ID:", process.env.CLIENT_ID?.slice(0, 6), "...");
  console.log("  EMAIL:", process.env.EMAIL);
  console.log("  TEAMS:", process.env.TEAMS);
  console.log("  WORKBOOK_ID:", process.env.WORKBOOK_ID || process.env.GETTING_STARTED_BASE_URL);
}
