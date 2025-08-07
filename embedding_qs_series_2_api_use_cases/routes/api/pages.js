// file: embedding_qs_series_2_api_use_cases/routes/api/pages.js

const express = require("express");
const router = express.Router();
const getBearerToken = require("../../helpers/get-access-token");

const BASE_URL = process.env.BASE_URL;

// GET /api/pages?workbookUrlId=...
router.get("/", async (req, res) => {
  const { workbookUrlId } = req.query;

  if (!workbookUrlId) {
    return res.status(400).json({ error: "Missing workbookUrlId" });
  }

  try {
    const token = await getBearerToken();

    const url = `${BASE_URL}/workbooks/${workbookUrlId}/pages`;
    const response = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
    });

    const raw = await response.text();

    if (process.env.DEBUG === "true") {
      console.log("Pages API response:", raw);
    }

    if (!response.ok) {
      throw new Error(`Sigma API error ${response.status}: ${raw}`);
    }

    const json = JSON.parse(raw);
    const allPages = Array.isArray(json.entries) ? json.entries : [];
    
    if (process.env.DEBUG === "true") {
      console.log("Page objects structure:", JSON.stringify(allPages, null, 2));
    }
    
    // Filter out hidden pages - they should not appear in embed dropdown
    const visiblePages = allPages.filter(page => {
      // Check various possible hidden/visibility flags
      if (page.hidden === true || page.isHidden === true || page.visible === false) {
        if (process.env.DEBUG === "true") {
          console.log(`Filtering out hidden page: ${page.name || page.pageId}`);
        }
        return false;
      }
      return true;
    });

    if (process.env.DEBUG === "true") {
      console.log(`Total pages: ${allPages.length}, Visible pages: ${visiblePages.length}`);
    }

    res.status(200).json({ entries: visiblePages });
  } catch (err) {
    console.error("Error fetching pages:", err.message);
    res.status(500).json({ error: err.message || "Failed to fetch pages" });
  }
});

module.exports = router;
