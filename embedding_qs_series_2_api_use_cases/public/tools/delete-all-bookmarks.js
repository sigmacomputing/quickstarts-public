// tools/delete-all-bookmarks.js

require("dotenv").config({ path: __dirname + "/../../.env" }); 

const getBearerToken = require("../../helpers/get-access-token");

async function deleteAllBookmarks(workbookId) {
  const clientId = process.env.CLIENT_ID;
  const clientSecret = process.env.SECRET;

  if (!clientId || !clientSecret) {
    throw new Error("Missing CLIENT_ID or SECRET in environment");
  }

  const token = await getBearerToken();
  if (!token) {
    throw new Error("Failed to obtain bearer token");
  }

  // Debug info
  console.log("Token obtained.");
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64"));
    console.log("Token payload (decoded):", payload);
  } catch {
    console.warn("Failed to decode token payload.");
  }

  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
  };

  const bookmarksUrl = `https://aws-api.sigmacomputing.com/v2/workbooks/${workbookId}/bookmarks`;
  console.log(`Fetching bookmarks from: ${bookmarksUrl}`);

  const res = await fetch(bookmarksUrl, { headers });
  const text = await res.text();

  console.log("Raw response:", text);

  let bookmarks;
  try {
    const json = JSON.parse(text);
    bookmarks = json.entries || [];
  } catch (err) {
    console.error("Failed to parse bookmarks list:", err.message);
    return;
  }

  console.log(`Parsed bookmark entries: ${bookmarks.length}`);
  if (bookmarks.length === 0) {
    console.log("🎉 No bookmarks found to delete.");
    return;
  }

  console.log(`Deleting ${bookmarks.length} bookmarks…`);
  for (const b of bookmarks) {
    const deleteUrl = `https://aws-api.sigmacomputing.com/v2/workbooks/${workbookId}/bookmarks/${b.bookmarkId}`;
    try {
      const delRes = await fetch(deleteUrl, {
        method: "DELETE",
        headers,
      });

      if (!delRes.ok) {
        const errText = await delRes.text();
        console.error(`Failed to delete ${b.name} (${b.bookmarkId}): ${delRes.status} ${errText}`);
      } else {
        console.log(`Deleted ${b.name} (${b.bookmarkId})`);
      }

      await new Promise((r) => setTimeout(r, 200)); // throttle
    } catch (err) {
      console.error(`Exception deleting ${b.name}: ${err.message}`);
    }
  }

  console.log("Done!");
}

// Run from CLI: `node tools/delete-all-bookmarks.js <workbookId>`
const workbookId = process.argv[2];
if (!workbookId) {
  console.error("Usage: node tools/delete-all-bookmarks.js <workbookId>");
  process.exit(1);
}

deleteAllBookmarks(workbookId);
