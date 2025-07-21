// File: embedding_qs_series_2_api_use_cases/routes/api/bookmarks_db.js
// API routes for bookmark operations with local database storage

const express = require("express");
const router = express.Router();
const getWorkbookMetadata = require("../../helpers/get-workbook-metadata");
const createBookmarkSigma = require("../../helpers/create-bookmark-sigma");
const db = require("../../helpers/local-bookmark-store");
const deleteBookmarkSigma = require("../../helpers/delete-bookmark-sigma");
const getBearerToken = require("../../helpers/get-access-token");

// Initialize DEBUG mode
const DEBUG = process.env.DEBUG === "true";

/**
 * GET /api/bookmarks_db/debug/all
 * Development endpoint to dump all bookmarks for debugging
 * @deprecated Should be removed in production
 */
router.get("/debug/all", async (req, res) => {
  try {
    const bookmarks = db.get("bookmarks").value();
    if (DEBUG) console.log("🔍 Dumping all bookmarks:\n", bookmarks);
    res.json({ bookmarks });
  } catch (err) {
    if (DEBUG) console.error("❌ Failed to dump bookmarks:", err);
    res.status(500).json({ error: "Could not load bookmarks" });
  }
});

/**
 * GET /api/bookmarks_db
 * Returns bookmarks filtered by workbookUrlId or specific bookmarkId
 * @query {string} workbookUrlId - Filter bookmarks by workbook
 * @query {string} bookmarkId - Get specific bookmark by ID
 */
router.get("/", async (req, res) => {
  try {
    const { bookmarkId, workbookUrlId } = req.query;

    let bookmarks = db.get("bookmarks").value();

    // If fetching a specific bookmark
    if (bookmarkId) {
      if (DEBUG) {
        console.log("🔎 Looking for bookmark ID:", bookmarkId);
        const allIds = bookmarks.map((bm) => bm.id);
        console.log("🧠 Available IDs:", allIds);
      }

      const bookmark = bookmarks.find((bm) => bm.id === bookmarkId);

      if (!bookmark) {
        if (DEBUG) console.warn("❌ Bookmark not found for ID:", bookmarkId);
        return res.status(404).json({
          error: "Bookmark not found - If fetching a specific bookmark",
        });
      }

      if (DEBUG) console.log("✅ Returning bookmark:", bookmark.name);
      return res.json({ bookmark });
    }

    // If filtering by workbook
    if (workbookUrlId) {
      if (DEBUG) console.log("🔍 Filtering bookmarks for:", workbookUrlId);
      bookmarks = bookmarks.filter((bm) => bm.workbookUrlId === workbookUrlId);
    }

    res.json({ bookmarks });
    if (DEBUG) console.log("✅ Returning bookmarks:", bookmarks.length);
  } catch (err) {
    if (DEBUG) console.error("Failed to fetch bookmarks:", err);
    res.status(500).json({ error: "Failed to load bookmarks" });
  }
});

/**
 * POST /api/bookmarks_db
 * Creates a new bookmark in Sigma and stores it in local database
 */
router.post("/", async (req, res) => {
  if (DEBUG) console.log("🔔 Incoming POST body:", req.body);
  try {
    const {
      bookmarkName,
      descr,
      isDefault,
      isShared,
      sharedWith,
      exploreKey,
      workbookUrlId,
      userEmail,
    } = req.body;

    const finalUserEmail = userEmail || "testuser@example.com";

    if (!bookmarkName || !exploreKey || !workbookUrlId) {
      if (DEBUG) {
        console.warn("Missing field(s):", {
          bookmarkName,
          exploreKey,
          workbookUrlId,
          userEmail: finalUserEmail,
        });
      }
      return res.status(400).json({ error: "Missing required fields" });
    }

    const metadata = await getWorkbookMetadata(workbookUrlId);

    const sigmaResult = await createBookmarkSigma({
      userEmail: finalUserEmail,
      workbookUrlId,
      exploreKey,
      name: bookmarkName,
    });

    // Store in lowdb
    db.get("bookmarks")
      .push({
        id: sigmaResult.bookmarkId,
        userEmail: finalUserEmail,
        workbookUrlId,
        exploreKey,
        name: bookmarkName,
        descr,
        isDefault,
        isShared,
        sharedWith,
      })
      .write();

    res.status(200).json({ success: true, bookmarkId: sigmaResult.bookmarkId });
  } catch (err) {
    if (DEBUG) console.error("Bookmark creation failed:", err);
    res.status(500).json({ error: "Failed to create bookmark" });
  }
});

/**
 * DELETE /api/bookmarks_db/bookmarks/:id
 * Deletes a bookmark from both Sigma and local database
 */
router.delete("/bookmarks/:id", async (req, res) => {
  if (DEBUG) console.log("🔥 DELETE route hit");
  const { id: bookmarkId } = req.params;
  const { userEmail, workbookId } = req.body;

  if (!userEmail || !workbookId) {
    return res.status(400).json({ error: "Missing userEmail or workbookId" });
  }

  try {
    // ❌ Delete from Sigma
    await deleteBookmarkSigma({ userEmail, workbookId, bookmarkId });

    // 🧹 Delete from local DB
    const bookmarks = db.get("bookmarks").value();
    const remaining = bookmarks.filter((b) => b.id !== bookmarkId);
    db.set("bookmarks", remaining).write();

    if (DEBUG) console.log(`✅ Deleted bookmark ${bookmarkId} for ${userEmail}`);
    res.json({ success: true });
  } catch (err) {
    if (DEBUG) console.error("❌ Failed to delete bookmark:", err);
    res.status(500).json({ error: "Failed to delete bookmark" });
  }
});

/**
 * DELETE /api/bookmarks_db/clear-all
 * Deletes all bookmarks for a workbook from both Sigma API and local database
 */
router.delete("/clear-all", async (req, res) => {
  if (DEBUG) console.log("🗑️ Clear all bookmarks route hit");
  
  const { workbookId, workbookUrlId, userEmail } = req.body;

  // Validation
  if (!workbookId || !workbookUrlId || !userEmail) {
    return res.status(400).json({ 
      error: "Missing required fields: workbookId, workbookUrlId, userEmail" 
    });
  }

  try {
    let deletedCount = 0;
    
    // Step 1: Get bearer token for Sigma API
    const token = await getBearerToken();
    if (!token) {
      throw new Error("Failed to obtain bearer token for Sigma API");
    }

    if (DEBUG) console.log("✅ Bearer token obtained for clear all operation");

    // Step 2: Fetch all bookmarks from Sigma API
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

    // Step 3: Delete all bookmarks from Sigma API
    for (const bookmark of sigmaBookmarks) {
      try {
        const deleteUrl = `${process.env.BASE_URL}/workbooks/${workbookId}/bookmarks/${bookmark.bookmarkId}`;
        
        const delRes = await fetch(deleteUrl, {
          method: "DELETE",
          headers,
        });

        if (delRes.ok) {
          deletedCount++;
          if (DEBUG) console.log(`✅ Deleted Sigma bookmark: ${bookmark.name} (${bookmark.bookmarkId})`);
        } else {
          const errText = await delRes.text();
          if (DEBUG) console.error(`❌ Failed to delete Sigma bookmark ${bookmark.name}: ${delRes.status} ${errText}`);
        }

        // Throttle API calls to avoid rate limiting
        await new Promise((resolve) => setTimeout(resolve, 200));
        
      } catch (err) {
        if (DEBUG) console.error(`Exception deleting Sigma bookmark ${bookmark.name}:`, err.message);
      }
    }

    // Step 4: Clear matching bookmarks from local database
    const localBookmarks = db.get("bookmarks").value();
    const bookmarksToKeep = localBookmarks.filter(bm => bm.workbookUrlId !== workbookUrlId);
    const localDeletedCount = localBookmarks.length - bookmarksToKeep.length;
    
    db.set("bookmarks", bookmarksToKeep).write();
    
    if (DEBUG) {
      console.log(`✅ Deleted ${localDeletedCount} bookmarks from local database`);
      console.log(`✅ Total bookmarks deleted: ${deletedCount} from Sigma, ${localDeletedCount} from local DB`);
    }

    res.json({ 
      success: true, 
      deletedCount: Math.max(deletedCount, localDeletedCount),
      sigmaDeleted: deletedCount,
      localDeleted: localDeletedCount
    });
    
  } catch (err) {
    if (DEBUG) console.error("❌ Clear all bookmarks failed:", err.message);
    res.status(500).json({ error: `Failed to clear all bookmarks: ${err.message}` });
  }
});

module.exports = router;
