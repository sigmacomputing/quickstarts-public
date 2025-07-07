// helpers/get-workbooks.js

const getBearerToken = require("./get-access-token");

/**
 * getWorkbooksByTeam - Calls Sigma API to retrieve workbooks and filters by workspace name.
 *
 * Sigma API: GET /v2/workbooks
 * https://api.sigmacomputing.com/v2/workbooks
 *
 * @param {string} teamName - The workspace path to filter on (defaults to process.env.WORKSPACE_NAME)
 * @returns {Promise<Array>} Filtered list of workbook objects: [{ id, name, url, path }]
 * @throws {Error} If API request fails or returns invalid format
 */
async function getWorkbooksByTeam(teamName = process.env.WORKSPACE_NAME) {
  const token = await getBearerToken();

  const response = await fetch(`${process.env.BASE_URL}/workbooks`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Workbook fetch failed: ${response.statusText}`);
  }

  const data = await response.json();

  // Filter workbooks by exact match to provided team/workspace path
  const filtered = data?.entries?.filter((w) => w.path === teamName);

  // Return only relevant metadata for downstream use
  return filtered.map((w) => ({
    id: w.workbookId,
    name: w.name,
    url: w.url,
    path: w.path,
  }));
}

module.exports = { getWorkbooksByTeam };
