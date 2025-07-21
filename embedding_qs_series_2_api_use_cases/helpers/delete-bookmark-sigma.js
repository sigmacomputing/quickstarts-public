// helpers/delete-bookmark-sigma.js
const axios = require("axios");
const dotenv = require("dotenv");
dotenv.config();
const getBearerToken = require("./get-access-token");

const BASE_URL = process.env.BASE_URL;

module.exports = async function deleteBookmarkSigma({
  userEmail,
  workbookId,
  bookmarkId,
}) {
  const token = await getBearerToken();

  if (!userEmail || !bookmarkId || !workbookId) {
    throw new Error("Missing userEmail, workbookId, or bookmarkId");
  }

  const url = `${BASE_URL}/workbooks/${workbookId}/bookmarks/${bookmarkId}`;

  await axios.delete(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-Sigma-User": userEmail,
    },
  });

  console.log(`✅ Deleted bookmark ${bookmarkId} from Sigma for ${userEmail}`);
};
