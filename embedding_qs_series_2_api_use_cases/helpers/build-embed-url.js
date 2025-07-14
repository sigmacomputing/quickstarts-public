// helpers/build-embed-url.js
const dotenv = require("dotenv");
dotenv.config();

const EMBED_URL_BASE = process.env.EMBED_URL_BASE;

/**
 * Builds a Sigma embed URL using workbookName and workbookUrlId,
 * and appends optional embed interface parameters from .env or request
 */
module.exports = function buildEmbedUrl({
  orgSlug,
  workbookName,
  workbookUrlId,
  embedType = "workbook",
  pageId = "",
  elementId = "",
  bookmarkId = "",

  // Allow override via request
  hide_folder_navigation,
  hide_menu,
  menu_position,
}) {
  if (!orgSlug || !workbookUrlId) {
    throw new Error("Missing orgSlug or workbookUrlId");
  }

  let path;

  if (embedType === "workbook") {
    if (!workbookName) {
      throw new Error("Missing workbookName for workbook embed");
    }
    path = `/workbook/${workbookName}-${workbookUrlId}`;
  } else if (embedType === "page") {
    if (!workbookName || !pageId) {
      throw new Error("Missing workbookName or pageId for page embed");
    }
    path = `/workbook/${workbookName}-${workbookUrlId}/page/${pageId}`;
  } else if (embedType === "element") {
    if (!workbookName || !pageId || !elementId) {
      throw new Error("Missing required info for element embed");
    }
    path = `/workbook/${workbookName}-${workbookUrlId}/element/${elementId}`;
  } else {
    throw new Error(`Unsupported embedType: ${embedType}`);
  }

  // Start with .env-based values
  const optionalParams = {
    disable_auto_refresh: process.env.disable_auto_refresh,
    disable_mobile_view: process.env.disable_mobile_view,
    hide_folder_navigation: process.env.hide_folder_navigation,
    hide_menu: process.env.hide_menu,
    hide_page_controls: process.env.hide_page_controls,
    hide_reload_button: process.env.hide_reload_button,
    hide_title: process.env.hide_title,
    hide_tooltip: process.env.hide_tooltip,
    hide_view_select: process.env.hide_view_select,
    lng: process.env.lng,
    menu_position: process.env.menu_position,
    responsive_height: process.env.responsive_height,
    theme: process.env.theme,
    view_id: process.env.view_id,
  };

  // Override specific ones if values were passed in
  if (typeof hide_folder_navigation !== "undefined")
    optionalParams.hide_folder_navigation = hide_folder_navigation;

  if (typeof hide_menu !== "undefined")
    optionalParams.hide_menu = hide_menu;

  if (typeof menu_position !== "undefined")
    optionalParams.menu_position = menu_position;

  const params = [];

  // Add bookmark if present
  if (bookmarkId) {
    params.push(`:bookmark=${bookmarkId}`);
  }

  params.push(":embed=true");

  for (const [key, val] of Object.entries(optionalParams)) {
    if (val && val !== "") {
      params.push(`:${key}=${encodeURIComponent(val)}`);
    }
  }

  const queryString = params.join("&");
  return `${EMBED_URL_BASE}/${orgSlug}${path}?${queryString}`;
};
