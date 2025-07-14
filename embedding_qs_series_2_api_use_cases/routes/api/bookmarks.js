const express = require("express");
const router = express.Router();
const createBookmark = require("../../helpers/create-bookmark");
const resolveWorkbookId = require("../../helpers/resolve-workbook-id");
const listBookmarksForWorkbook = require("../../helpers/list-bookmarks");

// POST /api/bookmarks/create-bookmark
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
    console.error("Bookmark creation error:", err.message);
    res.status(500).json({ error: err.message || "Unexpected server error" });
  }
});

// GET /api/bookmarks/list?workbookUrlId=abc123
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
    console.log("Matched workbook:", workbook.name);
    const workbookId = workbook.id;

    const bookmarks = await listBookmarksForWorkbook(workbookId);

    const entries = bookmarks.map((bm) => ({
      bookmarkId: bm.bookmarkId ?? bm.id,
      name: bm.name,
      exploreKey: bm.exploreKey,
    }));

    res.status(200).json({ entries });
  } catch (err) {
    console.error("Bookmark list error:", err.message);
    res.status(500).json({ error: err.message || "Failed to list bookmarks" });
  }
});

module.exports = router;
