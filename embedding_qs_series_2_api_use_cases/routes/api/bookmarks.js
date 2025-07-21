// File: embedding_qs_series_2_api_use_cases/routes/api/bookmarks.js
// API routes for Sigma bookmark operations (direct API integration)

const express = require("express");
const router = express.Router();
const createBookmark = require("../../helpers/create-bookmark");
const resolveWorkbookId = require("../../helpers/resolve-workbook-id");
const listBookmarksForWorkbook = require("../../helpers/list-bookmarks");

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

module.exports = router;
