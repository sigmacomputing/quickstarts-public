const express = require("express");
const router = express.Router();
const getWorkbookMetadata = require("../../helpers/get-workbook-metadata");
const createBookmarkSigma = require("../../helpers/create-bookmark-sigma");
const db = require("../../helpers/local-bookmark-store");
const deleteBookmarkSigma = require("../../helpers/delete-bookmark-sigma");
const DEBUG = process.env.DEBUG === "true";

// 🚨 TEMP: Dump all bookmarks for debugging
router.get("/debug/all", async (req, res) => {
  try {
    const bookmarks = db.get("bookmarks").value();
    console.log("🔍 Dumping all bookmarks:\n", bookmarks);
    res.json({ bookmarks });
  } catch (err) {
    console.error("❌ Failed to dump bookmarks:", err);
    res.status(500).json({ error: "Could not load bookmarks" });
  }
});

// ✅ GET bookmarks_db — return bookmarks filtered by workbookUrlId or bookmarkId
router.get("/", async (req, res) => {
  try {
    const { bookmarkId, workbookUrlId } = req.query;

    let bookmarks = db.get("bookmarks").value();

    // If fetching a specific bookmark
    if (bookmarkId) {
      console.log("🔎 Looking for bookmark ID:", bookmarkId);
      const allIds = bookmarks.map((bm) => bm.id);
      console.log("🧠 Available IDs:", allIds);

      const bookmark = bookmarks.find((bm) => bm.id === bookmarkId);

      if (!bookmark) {
        console.warn("❌ Bookmark not found for ID:", bookmarkId);
        return res.status(404).json({
          error: "Bookmark not found - If fetching a specific bookmark",
        });
      }

      console.log("✅ Returning bookmark:", bookmark.name);
      return res.json({ bookmark });
    }

    // If filtering by workbook
    if (workbookUrlId) {
      console.log("🔍 Filtering bookmarks for:", workbookUrlId);
      bookmarks = bookmarks.filter((bm) => bm.workbookUrlId === workbookUrlId);
    }

    res.json({ bookmarks });
    console.log("✅ Returning bookmarks:", bookmarks.length);
  } catch (err) {
    console.error("Failed to fetch bookmarks:", err);
    res.status(500).json({ error: "Failed to load bookmarks" });
  }
});

// ✅ POST bookmarks_db — create and store a bookmark
router.post("/", async (req, res) => {
  console.log("🔔 Incoming POST body:", req.body);
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
      console.warn("Missing field(s):", {
        bookmarkName,
        exploreKey,
        workbookUrlId,
        userEmail: finalUserEmail,
      });
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
    console.error("Bookmark creation failed:", err);
    res.status(500).json({ error: "Failed to create bookmark" });
  }
});

// delete from Sigma + local DB
router.delete("/bookmarks/:id", async (req, res) => {
  console.log("🔥 DELETE route hit");
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

    console.log(`✅ Deleted bookmark ${bookmarkId} for ${userEmail}`);
    res.json({ success: true });
  } catch (err) {
    console.error("❌ Failed to delete bookmark:", err);
    res.status(500).json({ error: "Failed to delete bookmark" });
  }
});

module.exports = router;
