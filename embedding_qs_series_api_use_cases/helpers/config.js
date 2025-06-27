// config.js

require("dotenv").config();

/**
 * Parse environment variable value as boolean.
 * Accepts 'true' (case-insensitive) as true, everything else is false.
 */
function parseBoolean(value) {
  return String(value).toLowerCase() === "true";
}

module.exports = {
  baseUrl: process.env.BASE_URL || "",

  // Auth-related
  email: process.env.EMAIL,
  clientId: process.env.CLIENT_ID,
  secret: process.env.SECRET,
  sessionLength: parseInt(process.env.SESSION_LENGTH, 10) || 3600,
  accountType: process.env.ACCOUNT_TYPE,
  teams: process.env.TEAMS?.split(",").map((t) => t.trim()) || [],
  evalConnectionId: process.env.eval_connection_id || null,

  // Member IDs for different roles
  memberIds: {
    admin: process.env.ADMIN_MEMBER_ID,
    build: process.env.BUILD_MEMBER_ID,
    view: process.env.VIEW_MEMBER_ID,
  },

  // Default workbook used by the "custom_workbook_list" QuickStart
  defaultWorkbookId: process.env.WORKBOOK_ID || null,

  // UI embed options (parsed as proper booleans or strings)
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
