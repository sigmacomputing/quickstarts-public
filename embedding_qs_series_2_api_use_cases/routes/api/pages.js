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
    const pages = Array.isArray(json.entries) ? json.entries : [];

    res.status(200).json({ entries: pages });
  } catch (err) {
    console.error("Error fetching pages:", err.message);
    res.status(500).json({ error: err.message || "Failed to fetch pages" });
  }
});

module.exports = router;
