// File: routes/api/elements.js

const express = require("express");
const router = express.Router();
const getBearerToken = require("../../helpers/get-access-token");

const BASE_URL = process.env.BASE_URL;

// GET /api/elements?workbookUrlId=...&pageId=...
router.get("/", async (req, res) => {
  const { workbookUrlId, pageId } = req.query;

  if (!workbookUrlId || !pageId) {
    return res.status(400).json({ error: "Missing workbookUrlId or pageId" });
  }

  try {
    const token = await getBearerToken();

    const url = `${BASE_URL}/workbooks/${workbookUrlId}/pages/${pageId}/elements`;
    const response = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
    });

    const raw = await response.text();

    if (process.env.DEBUG === "true") {
      console.log("Elements API response from Sigma:", raw);
    }

    if (!response.ok) {
      throw new Error(`Sigma API error ${response.status}: ${raw}`);
    }

    const json = JSON.parse(raw);
    const entries = Array.isArray(json.entries) ? json.entries : [];

    res.status(200).json({ entries });
  } catch (err) {
    console.error("Error fetching elements:", err.message);
    res.status(500).json({ error: err.message || "Failed to fetch elements" });
  }
});

module.exports = router;
