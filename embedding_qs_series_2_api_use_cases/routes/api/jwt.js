// File: embedding_qs_series_2_api_use_cases/routes/api/jwt.js

const express = require("express");
const router = express.Router();

const buildEmbedUrl = require("../../helpers/build-embed-url");
const getWorkbookMetadata = require("../../helpers/get-workbook-metadata");
const generateJwt = require("../../helpers/create-jwt");

// POST /api/jwt/:mode
router.post("/:mode", async (req, res) => {
  try {
    const { embedType = "workbook", workbookUrlId, targetId } = req.query;
    const mode = req.params.mode;
    const selectedUser = req.body?.sub || req.query?.sub;

    // Add this to destructure from the request body
    const {
      bookmarkId,
      hide_folder_navigation,
      hide_menu,
      menu_position,
    } = req.body;

    let pageId = "";
    let elementId = "";

    if (embedType === "element") {
      if (!targetId || !targetId.includes(":")) {
        return res
          .status(400)
          .json({ error: "Missing or invalid targetId for element embed" });
      }
      [pageId, elementId] = targetId.split(":");
    }

    if (!workbookUrlId) {
      return res.status(400).json({ error: "Missing workbookUrlId" });
    }

    const userMap = {
      view: process.env.VIEW_EMAIL,
      build: process.env.BUILD_EMAIL,
    };
    const sub = userMap[selectedUser] || selectedUser;

    const metadata = await getWorkbookMetadata(workbookUrlId);
    if (!metadata) {
      return res.status(404).json({ error: "Workbook not found" });
    }

    const {
      orgSlug,
      workbookName,
      workbookUrlId: parsedWorkbookUrlId,
    } = metadata;

    if (embedType === "page" && (!workbookName || !targetId)) {
      return res
        .status(400)
        .json({ error: "Missing workbookName or pageId for page embed" });
    }

    if (embedType === "element" && (!workbookName || !targetId)) {
      return res
        .status(400)
        .json({ error: "Missing workbookName or elementId for element embed" });
    }

    const embedUrl = buildEmbedUrl({
      orgSlug,
      workbookName,
      workbookUrlId: parsedWorkbookUrlId,
      embedType,
      pageId: embedType === "page" ? targetId : pageId,
      elementId: embedType === "element" ? elementId : "",
      bookmarkId,
      hide_folder_navigation,
      hide_menu,
      menu_position,
    });

    const jwt = generateJwt({ embedUrl, mode, sub });

    if (process.env.DEBUG === "true") {
      console.log("Embed URL:", embedUrl);
      if (bookmarkId) {
        console.log("With bookmarkId:", bookmarkId);
      }
    }

    const separator = embedUrl.includes("?") ? "&" : "?";
    res
      .status(200)
      .json({ embedUrl: `${embedUrl}${separator}:jwt=${jwt}`, jwt });
  } catch (err) {
    console.error("JWT generation error:", err.message);
    res.status(500).json({ error: "Failed to generate JWT" });
  }
});

module.exports = router;
