const getBearerToken = require("./get-access-token");
const getWorkbookMetadata = require("./get-workbook-metadata");
const BASE_URL = process.env.BASE_URL;

module.exports = async ({ userEmail, workbookUrlId, exploreKey, name }) => {
  const token = await getBearerToken();

  const metadata = await getWorkbookMetadata(workbookUrlId);
  const { workbookId, workbookVersion } = metadata;

  if (!workbookId || typeof workbookVersion !== "number") {
    throw new Error("Failed to retrieve workbookId or workbookVersion");
  }

  const payload = {
    workbookVersion,
    name,
    isShared: true,
    exploreKey,
  };

  if (process.env.DEBUG) {
    console.log("Bookmark metadata:", metadata);
    console.log("POST body:", JSON.stringify(payload, null, 2));
  }

  const response = await fetch(
    `${BASE_URL}/workbooks/${workbookId}/bookmarks`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );

  let json;
  try {
    json = await response.json();
  } catch (err) {
    const text = await response.text();
    throw new Error(`Sigma API ${response.status}: ${text}`);
  }

  if (!response.ok) {
    throw new Error(
      `Sigma API error ${response.status}: ${JSON.stringify(json)}`
    );
  }

  // Optional: return trimmed fields
  return {
    bookmarkId: json.bookmarkId ?? json.id,
    name: json.name,
    exploreKey: json.exploreKey,
  };
};
