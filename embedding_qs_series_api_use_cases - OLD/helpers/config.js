// helpers/config.js

require("dotenv").config();

/**
 * Parse an environment variable as a boolean.
 * Only accepts 'true' (case-insensitive) as true.
 */
function parseBoolean(value) {
  return String(value).toLowerCase() === "true";
}

module.exports = {
  // URL used to construct signed embed URL (if needed for override)
  baseUrl: process.env.BASE_URL || "",

  // Sigma API base (for provisioning, future expansion)
  apiBaseUrl: process.env.API_BASE_URL || "https://api.sigmacomputing.com/v2",

  // Auth-related
  email: process.env.EMAIL,
  clientId: process.env.CLIENT_ID,
  secret: process.env.SECRET, // used to sign JWT (HS256)
  sessionLength: parseInt(process.env.SESSION_LENGTH, 10) || 3600,
  accountType: process.env.ACCOUNT_TYPE || "embed", // optional; used for provisioning

  // Embed team membership (used in JWT payload)
  teams: process.env.TEAMS?.split(",").map(t => t.trim()).filter(Boolean) || [],

  // Optional eval-specific connection override
  evalConnectionId: process.env.eval_connection_id || null,

  // Embed user emails (used for provisioning)
  buildEmail: process.env.BUILD_EMAIL,
  viewEmail: process.env.VIEW_EMAIL,

  // Member IDs for impersonation (mapped from role strings)
  memberIds: {
    admin: process.env.ADMIN_MEMBER_ID,
    build: process.env.BUILD_MEMBER_ID,
    view: process.env.VIEW_MEMBER_ID,
  },

  // Target resource path (must be a full Sigma URL — workbook/page/element)
  defaultWorkbookId: process.env.WORKBOOK_ID || null,

  // UI-level embed options (for :param embedding, not used in JWT directly)
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

// Optional: helpful debug logging
if (process.env.DEBUG === "true") {
  console.log("Loaded config:");
  console.log("  CLIENT_ID:", process.env.CLIENT_ID?.slice(0, 6), "...");
  console.log("  EMAIL:", process.env.EMAIL);
  console.log("  TEAMS:", process.env.TEAMS);
  console.log("  WORKBOOK_ID:", process.env.WORKBOOK_ID);
}
