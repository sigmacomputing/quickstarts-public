const dotenv = require("dotenv");
dotenv.config();

const { getWorkbooksByTeam } = require("./get-workbooks");

/**
 * Given a workbookUrlId (short ID in URL), return the full workbook UUID.
 * @param {string} workbookUrlId
 * @returns {Promise<string>} The full workbookId (UUID)
 */
async function resolveWorkbookId(workbookUrlId) {
  const workbooks = await getWorkbooksByTeam();

  const match = workbooks.find((w) => {
    if (process.env.DEBUG === "true") {
      console.log("Comparing:", w.urlId, "vs", workbookUrlId);
    }
    return w.urlId === workbookUrlId;
  });

  if (!match) {
    throw new Error(`Could not find workbookId for URL id: ${workbookUrlId}`);
  }

  return match; // return full workbook object
}

module.exports = resolveWorkbookId;
