const { getWorkbooksByTeam } = require("./get-workbooks");

/**
 * getWorkbookMetadata - Fetches metadata for a given workbookUrlId.
 *
 * This helper wraps a call to getWorkbooksByTeam() and finds the matching workbook.
 * It extracts the orgSlug from the workbook URL and sanitizes the name for use in an embed URL.
 *
 * Sigma API: GET /v2/workbooks (via getWorkbooksByTeam)
 *
 * @param {string} workbookUrlId - The URL ID portion of the workbook URL (e.g., "f23kjsd").
 * @returns {Promise<Object>} An object with { orgSlug, workbookName, workbookUrlId }.
 * @throws {Error} If the workbook is not found in the list.
 */
module.exports = async function getWorkbookMetadata(workbookUrlId) {
  const workbooks = await getWorkbooksByTeam();

  const match = workbooks.find(wb =>
    wb.url?.endsWith(`/workbook/${workbookUrlId}`)
  );

  if (!match) {
    throw new Error(`Workbook not found for workbookUrlId: ${workbookUrlId}`);
  }

  // Extract the orgSlug from the URL (e.g., /orgSlug/workbook/abc123)
  const urlParts = match.url.split("/");
  const orgSlug = urlParts[3];

  // Replace spaces with underscores in workbookName to keep URL safe
  return {
    orgSlug,
    workbookName: match.name.replace(/\s+/g, "_"),
    workbookUrlId,
  };
};
