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

    const {
      bookmarkId,
      exploreKey,
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

    // 🔄 Map shorthand identifiers like "build" → actual email
    const userMap = {
      view: process.env.VIEW_EMAIL,
      build: process.env.BUILD_EMAIL,
    };
    const sub = userMap[selectedUser] || selectedUser;

    // ✅ Determine permissions based on actual user email
    let permissions = ["view"];
    if (sub === process.env.BUILD_EMAIL) {
      permissions = ["build"];
    }

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

    if (process.env.DEBUG === "true") {
      console.log("📨 JWT request body:", req.body);
      console.log("📘 embedType:", embedType);
      console.log("📗 workbookUrlId:", workbookUrlId);
      console.log("👤 selectedUser (sub):", sub);
      console.log("🔖 bookmarkId:", bookmarkId);
      console.log("🔑 exploreKey:", exploreKey);
    }

    const embedUrl = buildEmbedUrl({
      orgSlug,
      workbookName,
      workbookUrlId: parsedWorkbookUrlId,
      embedType,
      pageId: embedType === "page" ? targetId : pageId,
      elementId: embedType === "element" ? elementId : "",
      bookmarkId,
      exploreKey,
      hide_folder_navigation,
      hide_menu,
      menu_position,
    });

    // ✅ Now pass permissions explicitly
    const jwt = generateJwt({ embedUrl, mode, sub, permissions });

    if (process.env.DEBUG === "true") {
      console.log("Final embed URL:", embedUrl);
      console.log("JWT:", jwt);
    }

    const separator = embedUrl.includes("?") ? "&" : "?";
    res
      .status(200)
      .json({ embedUrl: `${embedUrl}${separator}:jwt=${jwt}`, jwt });
  } catch (err) {
    console.error("❌ JWT generation error:", err.message);
    res.status(500).json({ error: "Failed to generate JWT" });
  }
});

module.exports = router;
