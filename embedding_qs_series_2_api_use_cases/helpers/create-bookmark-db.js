const express = require("express");
const router = express.Router();
const { createBookmarkDb, deleteBookmarkDb, getBookmarkDb } = require("../../utils/lowdb");

module.exports = async ({ userEmail, workbookUrlId, exploreKey, name }) => {
  console.log("🧪 createBookmarkSigma input:", {
    userEmail,
    workbookUrlId,
    exploreKey,
    name,
  });

// GET all bookmarks
router.get("/", async (req, res) => {
  try {
    const bookmarks = await getBookmarkDb();
    res.json({ bookmarks });
  } catch (err) {
    console.error("Error fetching bookmarks:", err);
    res.status(500).json({ error: "Failed to get bookmarks" });
  }
});

// GET one bookmark by ID
router.get("/get", async (req, res) => {
  try {
    const { bookmarkId } = req.query;
    if (!bookmarkId) return res.status(400).json({ error: "Missing bookmarkId" });

    const bookmark = await getBookmarkDb(bookmarkId);
    res.json({ bookmark });
  } catch (err) {
    console.error("Error fetching bookmark:", err);
    res.status(500).json({ error: "Failed to get bookmark" });
  }
});

// POST to save (create or update) a bookmark
router.post("/", async (req, res) => {
  try {
    const { bookmarkName, descr, isDefault, isShared, sharedWith } = req.body;
    const { workbookUrlId, exploreKey, userEmail } = req.query;

    if (!workbookUrlId || !exploreKey || !userEmail || !bookmarkName) {
      return res.status(400).json({ error: "Missing required fields" });
    }

    const result = await createBookmarkDb({
      userEmail,
      workbookUrlId,
      exploreKey,
      name: bookmarkName,
      descr,
      isDefault,
      isShared,
      sharedWith,
    });

    res.status(200).json({ success: true, bookmarkId: result.bookmarkId });
  } catch (err) {
    console.error("Bookmark DB save error:", err);
    res.status(500).json({ error: "Failed to create bookmark" });
  }
});

// POST to delete a bookmark
router.post("/delete", async (req, res) => {
  try {
    const { bookmarkId, workbookUrlId } = req.body;

    if (!bookmarkId || !workbookUrlId) {
      return res.status(400).json({ error: "Missing bookmarkId or workbookUrlId" });
    }

    await deleteBookmarkDb(bookmarkId, workbookUrlId);

    res.status(200).json({ success: true });
  } catch (err) {
    console.error("Bookmark DB delete error:", err);
    res.status(500).json({ error: "Failed to delete bookmark" });
  }
});

module.exports = router;
