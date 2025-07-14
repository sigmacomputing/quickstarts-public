// File: embedding_qs_series_2_api_use_cases/helpers/list-bookmarks.js

const getBearerToken = require("./get-access-token");

/*** Fetch all bookmarks for a given workbook ID
 * @param {string} workbookId - Full UUID
 * @returns {Promise<Array>} Array of bookmarks
 */
async function listBookmarksForWorkbook(workbookId) {
  const token = await getBearerToken();

  const url = `${process.env.BASE_URL}/workbooks/${workbookId}/bookmarks`;
  if (process.env.DEBUG === "true") {
    console.log("Fetching bookmarks from:", url);
  }

  const res = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });

  const text = await res.text();

  if (process.env.DEBUG === "true") {
    console.log("Raw Sigma response:", text);
  }

  if (!res.ok) {
    throw new Error(`Bookmark fetch failed: ${res.status} ${res.statusText}`);
  }

  let data;
  try {
    data = JSON.parse(text);
  } catch (err) {
    throw new Error("Invalid JSON from Sigma: " + err.message);
  }

  if (process.env.DEBUG === "true") {
    console.log("Parsed bookmark entries:", data.entries?.length || 0);
  }

  return data.entries || [];
}

module.exports = listBookmarksForWorkbook;
