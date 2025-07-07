// routes/api/get-workbooks.js

const express = require("express");
const router = express.Router();
const { getWorkbooksByTeam } = require("../../helpers/get-workbooks");

/**
 * Sigma API: GET /v2/workbooks
 * This route fetches all workbooks visible to the authenticated API token.
 * It filters the results by team/workspace name, defaulting to WORKSPACE_NAME from env.
 * Used by the frontend dropdown to populate selectable workbooks.
 */

router.get("/", async (req, res) => {
  try {
    const team = req.query.team || process.env.WORKSPACE_NAME;
    const workbooks = await getWorkbooksByTeam(team);
    res.json({ workbooks });
  } catch (err) {
    console.error("Error fetching workbooks:", err);
    res.status(500).json({ error: err.message || "Failed to fetch workbooks" });
  }
});

module.exports = router;
