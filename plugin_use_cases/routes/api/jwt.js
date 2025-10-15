// File: plugin_use_cases/routes/api/jwt.js
// JWT generation for plugin hosting

const express = require("express");
const router = express.Router();
const generateJwt = require("../../helpers/create-jwt");
const { findWorkbookByName } = require("../../helpers/get-workbooks");
const buildEmbedUrl = require("../../helpers/build-embed-url");

// POST /api/jwt/:mode
router.post("/:mode", async (req, res) => {
  try {
    const { embedType = "workbook", workbookName, nodeId, bookmarkId } = req.query;
    const mode = req.params.mode;
    const selectedUser = req.body?.sub || req.query?.sub;

    // Use workbook name from query or env
    const targetWorkbook = workbookName || process.env.WORKBOOK_NAME;
    const workspace = process.env.WORKSPACE_NAME || process.env.VIEW_TEAMS;

    if (!targetWorkbook) {
      return res.status(400).json({ error: "Missing workbook name in query or WORKBOOK_NAME in env" });
    }

    if (!workspace) {
      return res.status(400).json({ error: "Missing WORKSPACE_NAME or VIEW_TEAMS in env" });
    }

    // Find workbook by name
    const workbook = await findWorkbookByName(targetWorkbook, workspace);
    if (!workbook) {
      // Get all workbooks for debugging
      const allWorkbooks = await require("../../helpers/get-workbooks").getWorkbooksByTeam(workspace);
      const workbookNames = allWorkbooks.map(w => w.name);
      
      return res.status(404).json({ 
        error: `Workbook "${targetWorkbook}" not found in workspace "${workspace}"`,
        availableWorkbooks: workbookNames,
        searchedWorkspace: workspace
      });
    }

    // Map shorthand identifiers like "build" -> actual email
    const userMap = {
      view: process.env.VIEW_EMAIL,
      build: process.env.BUILD_EMAIL,
      admin: process.env.BUILD_EMAIL,
    };
    const sub = userMap[selectedUser] || selectedUser;

    // Build proper embed URL using the helper
    let embedUrl;
    
    if (embedType === "element" && nodeId) {
      // For element embeds, build a direct URL since we only have nodeId
      const baseUrl = process.env.EMBED_URL_BASE || "https://app.sigmacomputing.com";
      embedUrl = `${baseUrl}/${process.env.ORG_SLUG}/workbook/${workbook.name}-${workbook.urlId}/element/${nodeId}?:embed=true`;
      
      // Add exploreKey if provided (for bookmark restoration)
      const { exploreKey } = req.query;
      if (exploreKey) {
        embedUrl += `&:explore_key=${encodeURIComponent(exploreKey)}`;
        if (process.env.DEBUG === "true") {
          console.log("Added exploreKey to element embed URL:", exploreKey.substring(0, 20) + "...");
        }
      }
    } else {
      // Use the helper for workbook embeds
      embedUrl = buildEmbedUrl({
        orgSlug: process.env.ORG_SLUG,
        workbookName: workbook.name,
        workbookUrlId: workbook.urlId,
        embedType: embedType,
        bookmarkId: bookmarkId
      });
    }

    // Generate JWT with plugin-specific configuration including team
    const userTeams = process.env.VIEW_TEAMS ? [process.env.VIEW_TEAMS] : [];
    const jwt = generateJwt({
      embedUrl,
      mode,
      sub,
      teams: userTeams,
    });

    if (process.env.DEBUG === "true") {
      console.log("Plugin workbook resolved:", workbook.name, "->", workbook.urlId);
      console.log("Plugin embed URL (before JWT):", embedUrl);
      console.log("Plugin JWT generated for user:", sub);
    }

    // Add JWT parameter to embed URL
    const separator = embedUrl.includes("?") ? "&" : "?";
    const finalEmbedUrl = `${embedUrl}${separator}:jwt=${jwt}`;

    if (process.env.DEBUG === "true") {
      console.log("Final embed URL (with JWT):", finalEmbedUrl);
    }

    res.json({ jwt, embedUrl: finalEmbedUrl, workbook: workbook.name });
  } catch (err) {
    console.error("JWT generation error:", err.message);
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;