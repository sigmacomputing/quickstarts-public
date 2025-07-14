// File: embedding_qs_series_2_api_use_cases/helpers/get-workbook-metadata.js

const { getWorkbooksByTeam } = require("./get-workbooks");

module.exports = async function getWorkbookMetadata(workbookUrlId) {
  const workbooks = await getWorkbooksByTeam();

  const match = workbooks.find((wb) =>
    wb.url?.endsWith(`/workbook/${workbookUrlId}`)
  );

  if (!match) {
    throw new Error(`Workbook not found for workbookUrlId: ${workbookUrlId}`);
  }

  const urlParts = match.url.split("/");
  const orgSlug = urlParts[3];

  if (process.env.DEBUG === "true") {
    console.log("Matched workbook metadata:", {
      id: match.id,
      name: match.name,
      url: match.url,
      latestVersion: match.latestVersion,
    });
  }

  return {
    orgSlug,
    workbookName: match.name.replace(/\s+/g, "_"),
    workbookUrlId,
    workbookId: match.id,
    workbookVersion: match.latestVersion,
  };
};
