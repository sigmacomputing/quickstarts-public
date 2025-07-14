// File: embedding_qs_series_2_api_use_cases/routes/api/workbooks.js

const express = require("express");
const router = express.Router();
const { getWorkbooksByTeam } = require("../../helpers/get-workbooks");

/**
 * Sigma API: GET /v2/workbooks
 * This route fetches all workbooks visible to the authenticated API token.
 * It filters by team/workspace name (from query or WORKSPACE_NAME env).
 */

router.get("/", async (req, res) => {
  try {
    const team = req.query.team || process.env.WORKSPACE_NAME;

    if (!team) {
      return res.status(400).json({ error: "Missing team or WORKSPACE_NAME" });
    }

    const workbooks = await getWorkbooksByTeam(team);

    if (process.env.DEBUG === "true") {
      console.log(`Workbooks retrieved for team "${team}":`, workbooks.length);
    }

    res.status(200).json({ workbooks });
  } catch (err) {
    console.error("Error fetching workbooks:", err.message);
    res.status(500).json({ error: err.message || "Failed to fetch workbooks" });
  }
});

module.exports = router;
