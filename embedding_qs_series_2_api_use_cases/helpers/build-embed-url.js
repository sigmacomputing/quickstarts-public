// helpers/build-embed-url.js
const BASE_URL = "https://app.sigmacomputing.com";

module.exports = function buildEmbedUrl({
  orgSlug,
  workbookName,
  workbookUrlId,
  embedType = "workbook",
  pageId = "",
  elementId = "",
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

  return `${BASE_URL}/${orgSlug}${path}`;
};

