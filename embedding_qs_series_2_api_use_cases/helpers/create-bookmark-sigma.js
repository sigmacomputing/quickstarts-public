// helpers/create-bookmark-sigma.js
const getBearerToken = require("./get-access-token");
const getWorkbookMetadata = require("./get-workbook-metadata");

const BASE_URL = process.env.BASE_URL;

module.exports = async ({ userEmail, workbookUrlId, exploreKey, name }) => {
  const token = await getBearerToken();

  const metadata = await getWorkbookMetadata(workbookUrlId);
  const { workbookId, workbookVersion } = metadata;

  if (!workbookId || typeof workbookVersion !== "number") {
    throw new Error("Missing workbook metadata");
  }

  const payload = {
    workbookVersion,
    name,
    isShared: true,
    exploreKey,
  };

  if (process.env.DEBUG === "true") {
    console.log("POST payload:", payload);
  }

  const response = await fetch(`${BASE_URL}/workbooks/${workbookId}/bookmarks`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const json = await response.json();

  if (!response.ok) {
    throw new Error(`Sigma API error ${response.status}: ${JSON.stringify(json)}`);
  }

  return {
    bookmarkId: json.bookmarkId ?? json.id,
    name: json.name,
    exploreKey: json.exploreKey,
  };
};
