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
  exploreKey = "",

  // Optional UI parameter overrides
  hide_folder_navigation,
  hide_menu,
  hide_page_controls,
  menu_position,
}) {
  if (!orgSlug || !workbookUrlId) {
    throw new Error("Missing orgSlug or workbookUrlId");
  }

  let path;
  if (embedType === "workbook") {
    if (!workbookName) throw new Error("Missing workbookName for workbook embed");
    path = `/workbook/${workbookName}-${workbookUrlId}`;
  } else if (embedType === "page") {
    if (!workbookName || !pageId) throw new Error("Missing workbookName or pageId for page embed");
    path = `/workbook/${workbookName}-${workbookUrlId}/page/${pageId}`;
  } else if (embedType === "element") {
    if (!workbookName || !pageId || !elementId)
      throw new Error("Missing required info for element embed");
    path = `/workbook/${workbookName}-${workbookUrlId}/element/${elementId}`;
  } else {
    throw new Error(`Unsupported embedType: ${embedType}`);
  }

  const optionalParams = {
    disable_auto_refresh: process.env.DISABLE_AUTO_REFRESH,
    disable_mobile_view: process.env.DISABLE_MOBILE_VIEW,
    hide_folder_navigation: process.env.HIDE_FOLDER_NAVIGATION,
    hide_menu: process.env.HIDE_MENU,
    hide_page_controls: process.env.HIDE_PAGE_CONTROLS,
    hide_reload_button: process.env.HIDE_RELOAD_BUTTON,
    hide_title: process.env.HIDE_TITLE,
    hide_tooltip: process.env.HIDE_TOOLTIP,
    hide_view_select: process.env.HIDE_VIEW_SELECT,
    lng: process.env.LNG,
    menu_position: process.env.MENU_POSITION,
    responsive_height: process.env.RESPONSIVE_HEIGHT,
    theme: process.env.THEME,
    view_id: process.env.VIEW_ID,
  };

  // Allow request-time overrides
  if (typeof hide_folder_navigation !== "undefined")
    optionalParams.hide_folder_navigation = hide_folder_navigation;

  if (typeof hide_menu !== "undefined")
    optionalParams.hide_menu = hide_menu;

  if (typeof hide_page_controls !== "undefined")
    optionalParams.hide_page_controls = hide_page_controls;

  if (typeof menu_position !== "undefined")
    optionalParams.menu_position = menu_position;

  const params = [];

  // IMPORTANT: Only one of these should be used — bookmark takes precedence
  if (bookmarkId) {
    params.push(`:bookmark=${encodeURIComponent(bookmarkId)}`);
  } else if (exploreKey) {
    params.push(`:explore=${encodeURIComponent(exploreKey)}`);
  }

  params.push(":embed=true");

  // Add optional embed UI parameters
  for (const [key, val] of Object.entries(optionalParams)) {
    if (val && val !== "") {
      params.push(`:${key}=${encodeURIComponent(val)}`);
    }
  }

  const queryString = params.join("&");
  return `${EMBED_URL_BASE}/${orgSlug}${path}?${queryString}`;
};