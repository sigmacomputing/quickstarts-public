// File: embedding_qs_series_2_api_use_cases/routes/api/bookmarks.js
// API routes for Sigma bookmark operations (direct API integration)

const express = require("express");
const router = express.Router();
const createBookmark = require("../../helpers/create-bookmark");
const resolveWorkbookId = require("../../helpers/resolve-workbook-id");
const listBookmarksForWorkbook = require("../../helpers/list-bookmarks");
const getBearerToken = require("../../helpers/get-access-token");

// Initialize DEBUG mode
const DEBUG = process.env.DEBUG === "true";

/**
 * POST /api/bookmarks/create-bookmark
 * Creates a new bookmark in Sigma for the specified user and workbook
 */
router.post("/create-bookmark", async (req, res) => {
  try {
    const { userEmail, workbookUrlId, exploreKey, name } = req.body;

    if (!userEmail || !workbookUrlId || !exploreKey || !name) {
      return res.status(400).json({ message: "Missing required fields" });
    }

    if (process.env.DEBUG === "true") {
      console.log("Creating bookmark:", {
        userEmail,
        workbookUrlId,
        name,
        exploreKey,
      });
    }

    const result = await createBookmark({
      userEmail,
      workbookUrlId,
      exploreKey,
      name,
    });

    res.status(200).json(result);
  } catch (err) {
    if (DEBUG) console.error("Bookmark creation error:", err.message);
    res.status(500).json({ error: err.message || "Unexpected server error" });
  }
});

/**
 * GET /api/bookmarks/list?workbookUrlId=abc123
 * Lists all bookmarks for a given workbook from Sigma API
 */
router.get("/list", async (req, res) => {
  try {
    const { workbookUrlId } = req.query;

    if (!workbookUrlId) {
      return res.status(400).json({ message: "Missing workbookUrlId" });
    }

    if (process.env.DEBUG === "true") {
      console.log("Listing bookmarks for workbookUrlId:", workbookUrlId);
    }

    const workbook = await resolveWorkbookId(workbookUrlId);
    if (DEBUG) console.log("Matched workbook:", workbook.name);
    const workbookId = workbook.id;

    const bookmarks = await listBookmarksForWorkbook(workbookId);

    const entries = bookmarks.map((bm) => ({
      bookmarkId: bm.bookmarkId ?? bm.id,
      name: bm.name,
      exploreKey: bm.exploreKey,
    }));

    res.status(200).json({ entries });
  } catch (err) {
    if (DEBUG) console.error("Bookmark list error:", err.message);
    res.status(500).json({ error: err.message || "Failed to list bookmarks" });
  }
});

/**
 * DELETE /api/bookmarks/clear-all
 * Deletes all bookmarks for a workbook from Sigma API
 */
router.delete("/clear-all", async (req, res) => {
  if (DEBUG) console.log("Clear all bookmarks route hit (direct API)");
  
  const { workbookUrlId, userEmail } = req.body;

  // Validation
  if (!workbookUrlId || !userEmail) {
    return res.status(400).json({ 
      error: "Missing required fields: workbookUrlId, userEmail" 
    });
  }

  try {
    let deletedCount = 0;
    
    // Step 1: Resolve workbook ID
    const workbook = await resolveWorkbookId(workbookUrlId);
    const workbookId = workbook.id;
    
    if (DEBUG) console.log("Resolved workbook ID:", workbookId);
    
    // Step 2: Get bearer token for Sigma API
    const token = await getBearerToken();
    if (!token) {
      throw new Error("Failed to obtain bearer token for Sigma API");
    }

    if (DEBUG) console.log("Bearer token obtained for clear all operation");

    // Step 3: Fetch all bookmarks from Sigma API
    const headers = {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    };

    const bookmarksUrl = `${process.env.BASE_URL}/workbooks/${workbookId}/bookmarks`;
    if (DEBUG) console.log(`Fetching bookmarks from Sigma API: ${bookmarksUrl}`);

    const res_sigma = await fetch(bookmarksUrl, { headers });
    const sigmaData = await res_sigma.json();
    const sigmaBookmarks = sigmaData.entries || [];

    if (DEBUG) console.log(`Found ${sigmaBookmarks.length} bookmarks in Sigma to delete`);

    // Step 4: Delete all bookmarks from Sigma API
    for (const bookmark of sigmaBookmarks) {
      try {
        const deleteUrl = `${process.env.BASE_URL}/workbooks/${workbookId}/bookmarks/${bookmark.bookmarkId}`;
        
        const delRes = await fetch(deleteUrl, {
          method: "DELETE",
          headers,
        });

        if (delRes.ok) {
          deletedCount++;
          if (DEBUG) console.log(`Deleted Sigma bookmark: ${bookmark.name} (${bookmark.bookmarkId})`);
        } else {
          const errText = await delRes.text();
          if (DEBUG) console.error(`Failed to delete Sigma bookmark ${bookmark.name}: ${delRes.status} ${errText}`);
        }

        // Throttle API calls to avoid rate limiting
        await new Promise((resolve) => setTimeout(resolve, 200));
        
      } catch (err) {
        if (DEBUG) console.error(`Exception deleting Sigma bookmark ${bookmark.name}:`, err.message);
      }
    }

    if (DEBUG) {
      console.log(`Clear all bookmarks completed - deleted ${deletedCount} bookmarks`);
    }

    res.json({ 
      success: true, 
      deletedCount: deletedCount,
      message: `Successfully deleted ${deletedCount} bookmarks`
    });
    
  } catch (err) {
    if (DEBUG) console.error("Clear all bookmarks failed:", err.message);
    res.status(500).json({ error: `Failed to clear all bookmarks: ${err.message}` });
  }
});

module.exports = router;
