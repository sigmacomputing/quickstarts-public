const express = require("express");
const router = express.Router();
const getBearerToken = require("../../helpers/get-access-token");

router.get("/", async (req, res) => {
  const { workbookUrlId, pageId } = req.query;

  if (!workbookUrlId || !pageId) {
    return res.status(400).json({ error: "Missing workbookUrlId or pageId" });
  }

  try {
    const token = await getBearerToken();

    const response = await fetch(
      `https://aws-api.sigmacomputing.com/v2/workbooks/${workbookUrlId}/pages/${pageId}/elements`,
      {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Sigma API failed: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    console.log("🔍 Raw elements API response from Sigma:", data);

    res.json({ entries: Array.isArray(data.entries) ? data.entries : [] });

  } catch (err) {
    console.error("❌ Failed to fetch elements:", err);
    res.status(500).json({ error: "Failed to fetch elements" });
  }
});

module.exports = router;
