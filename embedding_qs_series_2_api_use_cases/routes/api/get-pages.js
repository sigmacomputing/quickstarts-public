const express = require("express");
const router = express.Router();
const getBearerToken = require("../../helpers/get-access-token");

router.get("/", async (req, res) => {
  const { workbookUrlId } = req.query;

  if (!workbookUrlId) {
    return res.status(400).json({ error: "Missing workbookUrlId" });
  }

  try {
    const token = await getBearerToken();

    const response = await fetch(
      `https://aws-api.sigmacomputing.com/v2/workbooks/${workbookUrlId}/pages`,
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
    console.log("Pages received from Sigma:", data); // helpful

    res.json(data); // FIXED: no `.pages`
  } catch (err) {
    console.error("Failed to fetch pages:", err);
    res.status(500).json({ error: "Failed to fetch pages" });
  }
});

module.exports = router;
